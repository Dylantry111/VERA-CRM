"""Titan mailbox access over IMAP/SMTP. The caller supplies decrypted credentials."""
from __future__ import annotations

import email
import base64
import imaplib
import re
import smtplib
import ssl
from email import policy
from email.header import decode_header, make_header
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import formatdate, make_msgid
from html.parser import HTMLParser

IMAP_HOST = 'imap.titan.email'
SMTP_HOST = 'smtp.titan.email'
IMAP_PORT = 993
SMTP_PORT = 465
MAX_LIST = 100
MAX_MESSAGE_BYTES = 8 * 1024 * 1024


class MailboxError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def decode_header_value(value):
    if not value:
        return ''
    try:
        return str(make_header(decode_header(value)))
    except (LookupError, UnicodeError, TypeError):
        return str(value)


def connect(email_address, password):
    """Verify both receive and send credentials before saving them."""
    conn = None
    smtp = None
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=15)
        conn.login(email_address, password)
        smtp = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15, context=ssl.create_default_context())
        smtp.login(email_address, password)
        return True
    except (imaplib.IMAP4.error, smtplib.SMTPException, OSError, TimeoutError):
        raise MailboxError('Titan could not verify this mailbox. Check the address, app password and third-party access setting.') from None
    finally:
        if smtp:
            try:
                smtp.quit()
            except Exception:
                pass
        if conn:
            try:
                conn.logout()
            except Exception:
                pass


def open_imap(email_address, password):
    try:
        conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ssl.create_default_context(), timeout=20)
        conn.login(email_address, password)
        return conn
    except (imaplib.IMAP4.error, OSError, TimeoutError):
        raise MailboxError('Could not connect to the Titan mailbox. Reconnect it in Mail settings.') from None


def folders(email_address, password):
    conn = open_imap(email_address, password)
    try:
        status, rows = conn.list()
        if status != 'OK':
            raise MailboxError('Titan did not return the mailbox folders.')
        result = []
        for row in rows or []:
            if not row:
                continue
            flags = re.match(rb'\(([^)]*)\)\s+(?:"[^"]*"|\S+)\s+(.+)$', row)
            if not flags:
                continue
            raw_name = flags.group(2).strip()
            if raw_name.startswith(b'"') and raw_name.endswith(b'"'):
                raw_name = raw_name[1:-1].replace(b'\\"', b'"').replace(b'\\\\', b'\\')
            name = raw_name.decode('utf-8', errors='replace')
            folder_flags = flags.group(1).decode('ascii', errors='ignore').lower()
            result.append({'name': name, 'role': _folder_role(name, folder_flags)})
        result.sort(key=lambda item: (item['role'] not in ('inbox', 'sent'), item['name'].casefold()))
        return result
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _folder_role(name, flags=''):
    label = name.casefold()
    if '\\inbox' in flags or label == 'inbox':
        return 'inbox'
    if '\\sent' in flags or label in ('sent', 'sent items', 'sent messages'):
        return 'sent'
    if '\\trash' in flags or label in ('trash', 'deleted items', 'bin'):
        return 'trash'
    if '\\drafts' in flags or label == 'drafts':
        return 'drafts'
    if '\\archive' in flags or label == 'archive':
        return 'archive'
    return 'folder'


def _select(conn, folder, readonly=True):
    status, _ = conn.select(_quote_folder(folder), readonly=readonly)
    if status != 'OK':
        raise MailboxError('This mailbox folder could not be opened.')


def _quote_folder(folder):
    return '"' + folder.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _fetch_parts(conn, uid, query):
    status, data = conn.uid('fetch', str(uid), query)
    if status != 'OK':
        raise MailboxError('This email is no longer available in the mailbox.')
    return [part for part in (data or []) if isinstance(part, tuple) and len(part) > 1 and isinstance(part[1], bytes)]


def list_messages(email_address, password, folder, limit=50):
    limit = max(1, min(int(limit), MAX_LIST))
    conn = open_imap(email_address, password)
    try:
        _select(conn, folder, readonly=True)
        status, data = conn.uid('search', None, 'ALL')
        if status != 'OK':
            raise MailboxError('Could not search this mailbox folder.')
        ids = (data[0].split() if data and data[0] else [])[-limit:][::-1]
        messages = []
        if ids:
            status, fetched = conn.uid('fetch', ','.join(uid.decode('ascii') for uid in ids), '(FLAGS BODY.PEEK[HEADER.FIELDS (DATE FROM TO SUBJECT MESSAGE-ID)])')
            if status != 'OK':
                raise MailboxError('Could not retrieve the email list.')
        else:
            fetched = []
        for item in fetched or []:
            if not isinstance(item, tuple) or len(item) < 2 or not isinstance(item[1], bytes):
                continue
            meta = item[0].decode('ascii', errors='ignore')
            uid_match = re.search(r'\bUID\s+(\d+)', meta)
            if not uid_match:
                continue
            header = BytesParser(policy=policy.default).parsebytes(item[1])
            messages.append({
                'uid': uid_match.group(1),
                'from': decode_header_value(str(header.get('From', ''))),
                'to': decode_header_value(str(header.get('To', ''))),
                'subject': decode_header_value(str(header.get('Subject', ''))),
                'date': str(header.get('Date', '')),
                'message_id': str(header.get('Message-ID', '')),
                'unread': '\\Seen' not in meta,
            })
        return messages
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def get_message(email_address, password, folder, uid):
    conn = open_imap(email_address, password)
    try:
        _select(conn, folder, readonly=True)
        parts = _fetch_parts(conn, uid, '(FLAGS BODY.PEEK[])')
        if not parts:
            raise MailboxError('This email is no longer available in the mailbox.')
        raw = parts[0][1]
        if len(raw) > MAX_MESSAGE_BYTES:
            raise MailboxError('This email is too large to display in the mailbox.')
        message = BytesParser(policy=policy.default).parsebytes(raw)
        body, attachments = _body_and_attachments(message)
        meta = parts[0][0].decode('ascii', errors='ignore')
        return {
            'uid': str(uid), 'from': decode_header_value(str(message.get('From', ''))),
            'to': decode_header_value(str(message.get('To', ''))),
            'cc': decode_header_value(str(message.get('Cc', ''))),
            'subject': decode_header_value(str(message.get('Subject', ''))),
            'date': str(message.get('Date', '')), 'message_id': str(message.get('Message-ID', '')),
            'in_reply_to': str(message.get('Message-ID', '')), 'body': body,
            'unread': '\\Seen' not in meta, 'attachments': attachments,
        }
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def _body_and_attachments(message):
    plain = []
    html_body = []
    attachments = []
    part_index = 0
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        content_type = part.get_content_type()
        if filename or part.get_content_disposition() == 'attachment':
            attachments.append({'part': part_index, 'filename': decode_header_value(filename or f'attachment-{part_index}'), 'content_type': content_type})
            part_index += 1
            continue
        if content_type not in ('text/plain', 'text/html'):
            continue
        payload = part.get_payload(decode=True) or b''
        charset = part.get_content_charset() or 'utf-8'
        text = payload.decode(charset, errors='replace')
        if content_type == 'text/plain':
            plain.append(text)
        else:
            html_body.append(text)
    body = '\n\n'.join(plain).strip()
    if not body and html_body:
        extractor = _TextExtractor()
        for html in html_body:
            extractor.feed(html)
        body = '\n'.join(extractor.parts)
    return body, attachments


def attachment(email_address, password, folder, uid, part_index):
    conn = open_imap(email_address, password)
    try:
        _select(conn, folder, readonly=True)
        parts = _fetch_parts(conn, uid, '(BODY.PEEK[])')
        if not parts:
            raise MailboxError('This email is no longer available in the mailbox.')
        message = BytesParser(policy=policy.default).parsebytes(parts[0][1])
        idx = 0
        for part in message.walk():
            if part.is_multipart():
                continue
            if part.get_filename() or part.get_content_disposition() == 'attachment':
                if idx == int(part_index):
                    data = part.get_payload(decode=True) or b''
                    if len(data) > MAX_MESSAGE_BYTES:
                        raise MailboxError('This attachment is too large to download.')
                    return {'filename': decode_header_value(part.get_filename() or f'attachment-{idx}'), 'content_type': part.get_content_type(), 'data': data}
                idx += 1
        raise MailboxError('This attachment is no longer available.')
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def mark_read(email_address, password, folder, uid, read):
    conn = open_imap(email_address, password)
    try:
        _select(conn, folder, readonly=False)
        mode = '+FLAGS.SILENT' if read else '-FLAGS.SILENT'
        status, _ = conn.uid('store', str(uid), mode, '(\\Seen)')
        if status != 'OK':
            raise MailboxError('Could not update the read status.')
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def move_message(email_address, password, source, uid, destination):
    conn = open_imap(email_address, password)
    try:
        _select(conn, source, readonly=False)
        status, _ = conn.uid('copy', str(uid), _quote_folder(destination))
        if status != 'OK':
            raise MailboxError('Could not move this email to the selected folder.')
        conn.uid('store', str(uid), '+FLAGS.SILENT', '(\\Deleted)')
        conn.expunge()
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def delete_message(email_address, password, folder, uid):
    conn = open_imap(email_address, password)
    try:
        _select(conn, folder, readonly=False)
        conn.uid('store', str(uid), '+FLAGS.SILENT', '(\\Deleted)')
        conn.expunge()
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def send(email_address, password, recipient, subject, body, cc='', reply_to='', html_body=None, attachments=None):
    if '\r' in subject or '\n' in subject:
        raise MailboxError('The email subject is invalid.')
    message = EmailMessage()
    message['From'] = email_address
    message['To'] = recipient
    if cc.strip():
        message['Cc'] = cc.strip()
    if reply_to.strip():
        message['In-Reply-To'] = reply_to.strip()
        message['References'] = reply_to.strip()
    message['Subject'] = subject.strip()
    message['Date'] = formatdate(localtime=False)
    message['Message-ID'] = make_msgid()
    message.set_content(body)
    if html_body:
        inline_images = []
        def embed_image(match):
            try:
                payload = base64.b64decode(match.group(2), validate=True)
            except (ValueError, base64.binascii.Error):
                raise MailboxError('The signature image is invalid.') from None
            if len(payload) > 1024 * 1024:
                raise MailboxError('The signature image must be 1 MB or smaller.')
            subtype = match.group(1).lower()
            content_id = make_msgid().strip('<>')
            inline_images.append((payload, subtype, content_id))
            return f'cid:{content_id}'
        html_body = re.sub(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)', embed_image, html_body)
        message.add_alternative(html_body, subtype='html')
        if inline_images:
            html_part = message.get_payload()[-1]
            for payload, subtype, content_id in inline_images:
                html_part.add_related(payload, maintype='image', subtype=subtype, cid=f'<{content_id}>', disposition='inline')
    for filename, content_type, payload in attachments or []:
        maintype, _, subtype = content_type.partition('/')
        if not maintype or not subtype:
            maintype, subtype = 'application', 'octet-stream'
        message.add_attachment(payload, maintype=maintype, subtype=subtype, filename=filename)
    recipients = [entry.strip() for entry in re.split(r'[,;]', recipient + ',' + cc) if entry.strip()]
    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as client:
            client.login(email_address, password)
            client.send_message(message, to_addrs=recipients)
    except (smtplib.SMTPException, OSError, TimeoutError):
        raise MailboxError('Titan could not send the email. Check the mailbox connection and recipient address.') from None
    # Titan may expose an IMAP Sent folder under a localized name; use its \Sent flag when present.
    conn = open_imap(email_address, password)
    sent_folder = None
    try:
        status, rows = conn.list()
        for row in rows or []:
            if row and b'\\sent' in row.lower():
                match = re.search(rb'\s("(?:[^"\\]|\\.)*"|\S+)$', row)
                if match:
                    sent_folder = match.group(1).strip(b'"').decode('utf-8', errors='replace')
                    break
        if sent_folder:
            conn.append(_quote_folder(sent_folder), '(\\Seen)', imaplib.Time2Internaldate(email.utils.parsedate_to_datetime(message['Date']).timestamp()), message.as_bytes())
    except Exception:
        # A sent message should stay sent even if the Sent folder copy is temporarily unavailable.
        pass
    finally:
        try:
            conn.logout()
        except Exception:
            pass
    return message['Message-ID']
