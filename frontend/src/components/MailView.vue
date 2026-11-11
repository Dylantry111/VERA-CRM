<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import { Mail, RefreshCw, PenLine, Archive, Trash2, Reply, Paperclip, X, Settings, Plus, UserRound, ImagePlus, Save } from "lucide-vue-next";

const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
type MailStatus = { connected: boolean; credential_saved: boolean; credential_valid: boolean; email: string; provider: string; encryption_key_configured: boolean };
type MailFolder = { name: string; role: string };
type MailRow = { uid: string; from: string; to: string; subject: string; date: string; message_id: string; unread: boolean };
type MailAttachment = { part: number; filename: string; content_type: string };
type MailMessage = MailRow & { cc: string; in_reply_to: string; body: string; attachments: MailAttachment[] };
type MailTemplate = { id: string; name: string; subject: string; body: string };
type MailPreferences = { templates: MailTemplate[]; signature_text: string; signature_image_data: string };
type Customer = { customer_id: number; company: string; contact_name: string; email: string; customer_type?: string };
const status = ref<MailStatus | null>(null);
const folders = ref<MailFolder[]>([]);
const rows = ref<MailRow[]>([]);
const message = ref<MailMessage | null>(null);
const activeFolder = ref("");
const search = ref("");
const loading = ref(false);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const setup = reactive({ email: "Dylan@verashading.com", app_password: "" });
const customers = ref<Customer[]>([]);
const customerSearch = ref("");
const selectedCustomerIds = ref<number[]>([]);
const preferences = ref<MailPreferences>({ templates: [], signature_text: "", signature_image_data: "" });
const settingsOpen = ref(false);
const templateDraft = reactive({ id: "", name: "", subject: "", body: "" });
const templateSelected = ref("");
const imageInput = ref<HTMLInputElement | null>(null);
const messagePurpose = ref("existing_notice");
const consentConfirmed = ref(false);
const consentSource = ref("");
const composeOpen = ref(false);
const compose = reactive({ to: "", cc: "", subject: "", body: "", reply_to: "" });
const visibleRows = computed(() => {
  const term = search.value.trim().toLowerCase();
  return term ? rows.value.filter(row => `${row.from} ${row.subject} ${row.to}`.toLowerCase().includes(term)) : rows.value;
});
const unreadCount = computed(() => rows.value.filter(row => row.unread).length);
const archiveFolder = computed(() => folders.value.find(folder => folder.role === "archive" || /archive/i.test(folder.name))?.name || "");
const selectedIsUnread = computed(() => rows.value.find(row => row.uid === message.value?.uid)?.unread ?? false);
const visibleCustomers = computed(() => {
  const term = customerSearch.value.trim().toLowerCase();
  return customers.value.filter(row => row.email && (!term || `${row.company} ${row.contact_name} ${row.email}`.toLowerCase().includes(term)));
});

async function loadStatus() {
  error.value = "";
  try {
    status.value = await request<MailStatus>("operations/mailbox");
    if (status.value.connected) {
      await Promise.all([loadFolders(), loadMailPreferences(), loadCustomers()]);
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
}

async function loadCustomers() {
  try { customers.value = (await request<Customer[]>("operations/customers")).filter(row => !row.customer_type || row.customer_type === "wholesale"); }
  catch { customers.value = []; }
}

async function loadMailPreferences() {
  try { preferences.value = await request<MailPreferences>("operations/mailbox/preferences"); }
  catch { preferences.value = { templates: [], signature_text: "", signature_image_data: "" }; }
}

function toggleCustomerRecipient(customer: Customer) {
  selectedCustomerIds.value = selectedCustomerIds.value.includes(customer.customer_id)
    ? selectedCustomerIds.value.filter(id => id !== customer.customer_id)
    : [...selectedCustomerIds.value, customer.customer_id];
  compose.to = customers.value.filter(row => selectedCustomerIds.value.includes(row.customer_id)).map(row => row.email).join(", ");
}

function loadTemplate(id: string) {
  const template = preferences.value.templates.find(row => row.id === id);
  if (!template) return;
  compose.subject = template.subject;
  compose.body = template.body;
}

function editTemplate(id = "") {
  const template = preferences.value.templates.find(row => row.id === id);
  Object.assign(templateDraft, template || { id: crypto.randomUUID(), name: "", subject: "", body: "" });
}

async function saveTemplate() {
  if (!templateDraft.name.trim()) return;
  const next = { ...templateDraft, id: templateDraft.id || crypto.randomUUID() };
  const existing = preferences.value.templates.findIndex(row => row.id === next.id);
  if (existing >= 0) preferences.value.templates.splice(existing, 1, next);
  else preferences.value.templates.push(next);
  await saveMailPreferences();
}

async function saveMailPreferences() {
  busy.value = true; error.value = ""; notice.value = "";
  try {
    preferences.value = await request<MailPreferences>("operations/mailbox/preferences", preferences.value);
    notice.value = tx("邮件模板与签名已保存。", "Email templates and signature saved.");
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

function readSignatureImage(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 1024 * 1024) {
    error.value = tx("请使用不超过 1 MB 的 PNG、JPEG 或 WebP 图片。", "Choose a PNG, JPEG or WebP image under 1 MB.");
    return;
  }
  const reader = new FileReader();
  reader.onload = () => { preferences.value.signature_image_data = String(reader.result || ""); };
  reader.readAsDataURL(file);
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, char => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char] || char));
}

async function loadFolders() {
  if (!status.value?.connected) return;
  loading.value = true;
  try {
    folders.value = await request<MailFolder[]>("operations/mailbox/folders");
    const inbox = folders.value.find(folder => folder.role === "inbox") || folders.value[0];
    if (inbox && !folders.value.some(folder => folder.name === activeFolder.value)) activeFolder.value = inbox.name;
    if (activeFolder.value) await loadMessages();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
}

async function loadMessages() {
  if (!activeFolder.value) return;
  loading.value = true; error.value = ""; message.value = null;
  try { rows.value = await request<MailRow[]>(`operations/mailbox/messages?folder=${encodeURIComponent(activeFolder.value)}&limit=75`); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
}

async function openMessage(row: MailRow) {
  loading.value = true; error.value = "";
  try {
    message.value = await request<MailMessage>(`operations/mailbox/messages/${encodeURIComponent(row.uid)}?folder=${encodeURIComponent(activeFolder.value)}`);
    if (row.unread) {
      await request("operations/mailbox/read", { folder: activeFolder.value, uid: row.uid, read: true });
      row.unread = false;
    }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
}

async function connectMailbox() {
  busy.value = true; error.value = ""; notice.value = "";
  try {
    const result = await request<{ connected: boolean; email: string; provider: string }>("operations/mailbox/connect", { email: setup.email.trim(), app_password: setup.app_password });
    setup.app_password = "";
    status.value = { connected: result.connected, credential_saved: true, credential_valid: true, email: result.email, provider: result.provider, encryption_key_configured: true };
    notice.value = tx("邮箱已连接。","Mailbox connected.");
    await loadFolders();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

async function disconnectMailbox() {
  if (!window.confirm(tx("断开后后台将删除保存的连接凭据。确认继续？","Disconnecting removes the saved mailbox credential. Continue?"))) return;
  busy.value = true; error.value = "";
  try {
    await request("operations/mailbox/disconnect", {});
    status.value = { ...(status.value as MailStatus), connected: false, credential_saved: false, credential_valid: false, email: "" };
    folders.value = []; rows.value = []; message.value = null; activeFolder.value = "";
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

function openCompose(reply = false) {
  compose.to = reply && message.value ? (message.value.from.match(/<([^>]+)>/)?.[1] || message.value.from) : "";
  compose.cc = "";
  compose.subject = reply && message.value ? (/^re:/i.test(message.value.subject) ? message.value.subject : `Re: ${message.value.subject}`) : "";
  compose.body = reply && message.value ? `\n\n--- ${tx("原邮件","Original message")} ---\n${message.value.body}` : "";
  compose.reply_to = reply ? message.value?.in_reply_to || "" : "";
  selectedCustomerIds.value = [];
  customerSearch.value = "";
  messagePurpose.value = "existing_notice";
  consentConfirmed.value = false;
  consentSource.value = "";
  templateSelected.value = "";
  composeOpen.value = true;
}

async function sendMessage() {
  busy.value = true; error.value = ""; notice.value = "";
  try {
    const recipients = [...new Set(compose.to.split(/[,;\s]+/).map(value => value.trim()).filter(Boolean))];
    if (!recipients.length) throw new Error(tx("请选择至少一位收件人。", "Choose at least one recipient."));
    if (recipients.length > 1 && compose.cc.trim()) throw new Error(tx("为保护收件人隐私，逐封发送时请清空 CC。", "Clear CC when sending separately to multiple recipients."));
    const commercial = messagePurpose.value !== "existing_notice";
    if (commercial && (!consentConfirmed.value || !consentSource.value.trim())) {
      throw new Error(tx("商业邮件需要确认收件人同意，并记录同意依据。", "Commercial email requires confirmed recipient consent and a recorded consent source."));
    }
    const unsubscribe = commercial ? `<p style=\"font-size:12px;color:#687984\">To stop receiving further commercial emails, reply to <a href=\"mailto:${escapeHtml(status.value?.email || '')}?subject=UNSUBSCRIBE\">the sender</a> with UNSUBSCRIBE.</p>` : "";
    const signatureText = preferences.value.signature_text.split(/\r?\n/).map(escapeHtml).join("<br>");
    const signatureImage = preferences.value.signature_image_data ? `<p><img src=\"${preferences.value.signature_image_data}\" alt=\"VERA Shading Solutions\" style=\"max-width:240px;max-height:90px\"></p>` : "";
    const signatureHtml = signatureText || signatureImage ? `<div style=\"margin-top:20px;padding-top:12px;border-top:1px solid #d6e0e5\">${signatureText ? `<p>${signatureText}</p>` : ""}${signatureImage}</div>` : "";
    const plainBody = [compose.body, preferences.value.signature_text, commercial ? `To stop receiving further commercial emails, reply to ${status.value?.email || 'the sender'} with UNSUBSCRIBE.` : ""].filter(Boolean).join("\n\n");
    const htmlBody = `<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#304451\">${escapeHtml(compose.body).replace(/\r?\n/g, "<br>")}${signatureHtml}${unsubscribe}</div>`;
    let sentCount = 0;
    for (const recipient of recipients) {
      await request("operations/mailbox/send", { ...compose, body: plainBody, to: recipient, cc: recipients.length > 1 ? "" : compose.cc, html_body: htmlBody, purpose: messagePurpose.value, consent_confirmed: consentConfirmed.value, consent_source: consentSource.value.trim() });
      sentCount++;
    }
    composeOpen.value = false;
    notice.value = tx(`已分别发送 ${sentCount} 封邮件。`, `${sentCount} individual email(s) sent.`);
    const sent = folders.value.find(folder => folder.role === "sent");
    if (sent) { activeFolder.value = sent.name; await loadMessages(); }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

async function toggleRead() {
  if (!message.value) return;
  busy.value = true; error.value = "";
  try {
    await request("operations/mailbox/read", { folder: activeFolder.value, uid: message.value.uid, read: selectedIsUnread.value });
    const row = rows.value.find(item => item.uid === message.value?.uid);
    if (row) row.unread = !selectedIsUnread.value;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

async function moveToArchive() {
  if (!message.value || !archiveFolder.value) return;
  busy.value = true; error.value = "";
  try { await request("operations/mailbox/move", { folder: activeFolder.value, uid: message.value.uid, destination: archiveFolder.value }); await loadMessages(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

async function deleteMessage() {
  if (!message.value || !window.confirm(tx("确定从邮箱中删除这封邮件？","Delete this email from the mailbox?"))) return;
  busy.value = true; error.value = "";
  try { await request("operations/mailbox/delete", { folder: activeFolder.value, uid: message.value.uid }); await loadMessages(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

async function downloadAttachment(attachment: MailAttachment) {
  if (!message.value) return;
  error.value = "";
  try {
    const url = `/api/operations/mailbox/messages/${encodeURIComponent(message.value.uid)}/attachments/${attachment.part}?folder=${encodeURIComponent(activeFolder.value)}`;
    const response = await fetch(url, { headers: session.token ? { Authorization: `Bearer ${session.token}` } : {} });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || response.statusText);
    const blob = await response.blob(); const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = objectUrl; anchor.download = attachment.filename; anchor.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
}

function folderLabel(folder: MailFolder) {
  const labels: Record<string, [string, string]> = { inbox: ["收件箱", "Inbox"], sent: ["已发送", "Sent"], drafts: ["草稿", "Drafts"], archive: ["归档", "Archive"], trash: ["垃圾箱", "Trash"] };
  return labels[folder.role] ? tx(...labels[folder.role]!) : folder.name;
}

onMounted(() => void loadStatus());
</script>

<template>
  <section class="mail-workspace">
    <header class="mail-page-head"><div><p class="eyebrow">VERA · COMMUNICATIONS</p><h1>{{ tx("邮件","Mail") }}</h1><p>{{ tx("在后台查看并管理企业邮箱。","View and manage your business mailbox from the admin workspace.") }}</p></div><div v-if="status?.connected" class="mail-head-actions"><span class="connected-pill">{{ status.email }}</span><button type="button" class="mail-icon-button" :disabled="loading" :aria-label="tx('刷新邮件','Refresh mail')" @click="loadMessages"><RefreshCw :size="16" /></button><button type="button" class="mail-icon-button" :aria-label="tx('邮件模板与签名设置','Email template and signature settings')" @click="settingsOpen=true;editTemplate(templateSelected)"><Settings :size="16" /> {{ tx('邮件设置','Mail settings') }}</button><button type="button" class="mail-primary" @click="openCompose()"><PenLine :size="15" /> {{ tx("写邮件","Compose") }}</button></div></header>
    <p v-if="error" class="mail-error" role="alert">{{ error }}</p><p v-if="notice" class="mail-notice" role="status">{{ notice }}</p>
    <section v-if="!status?.connected" class="mail-connect-card">
      <div class="mail-connect-icon"><Mail :size="22" /></div><h2>{{ tx("连接 Titan 邮箱","Connect Titan mailbox") }}</h2><p>{{ tx("已识别邮箱地址 Dylan@verashading.com。连接后，后台会直接从 Titan 同步文件夹和邮件。","Mailbox address identified as Dylan@verashading.com. Once connected, folders and emails are read directly from Titan.") }}</p>
      <div v-if="status && !status.encryption_key_configured" class="mail-key-notice"><strong>{{ tx("需要先完成一次服务器安全设置","One server security setting is required first") }}</strong><span>{{ tx("请在 Vercel 项目的环境变量中添加 VERA_MAIL_ENCRYPTION_KEY（Fernet 格式密钥）。它用于加密邮箱应用密码后再保存。","Add VERA_MAIL_ENCRYPTION_KEY (a Fernet key) to the Vercel project environment. It encrypts the mailbox app password before it is stored.") }}</span></div>
      <div v-else-if="status?.credential_saved && !status.credential_valid" class="mail-key-notice"><strong>{{ tx("需要重新连接邮箱","Reconnect the mailbox") }}</strong><span>{{ tx("已保存的邮箱凭据无法用当前服务器密钥解密。请确认 VERA_MAIL_ENCRYPTION_KEY 与保存凭据时相同；如果密钥已更换，请重新输入 Titan 应用专用密码。","The saved mailbox credential cannot be decrypted with the current server key. Restore the original VERA_MAIL_ENCRYPTION_KEY, or enter the Titan app password again if that key was changed.") }}</span></div>
      <form @submit.prevent="connectMailbox"><label>{{ tx("企业邮箱","Business email") }}<input v-model.trim="setup.email" type="email" autocomplete="username" required /></label><label>{{ tx("Titan 应用专用密码","Titan app password") }}<input v-model="setup.app_password" type="password" autocomplete="new-password" required /></label><p class="mail-help">{{ tx("请在 Titan 开启第三方应用访问；如果邮箱开启了双重验证，请使用应用专用密码。此密码不会显示在页面或返回给浏览器。","Enable third-party app access in Titan. If two-factor authentication is on, use an app password. The credential is never returned to the browser after saving.") }}</p><button type="submit" class="mail-primary" :disabled="busy || (status !== null && !status.encryption_key_configured)">{{ busy ? tx("正在验证…","Verifying…") : tx("安全连接邮箱","Connect securely") }}</button></form>
    </section>
    <section v-else class="mail-client">
      <aside class="mail-sidebar"><button v-for="folder in folders" :key="folder.name" type="button" class="mail-folder" :class="{ active: activeFolder === folder.name }" @click="activeFolder=folder.name;loadMessages()"><Mail :size="15" /><span>{{ folderLabel(folder) }}</span><b v-if="folder.role==='inbox' && unreadCount">{{ unreadCount }}</b></button><button type="button" class="disconnect-link" @click="disconnectMailbox">{{ tx("断开邮箱连接","Disconnect mailbox") }}</button></aside>
      <div class="mail-message-list"><div class="mail-list-toolbar"><h2>{{ folderLabel(folders.find(folder=>folder.name===activeFolder) || {name:activeFolder,role:'folder'}) }}</h2><input v-model="search" :placeholder="tx('搜索邮件','Search mail')" /><span>{{ visibleRows.length }}</span></div><button v-for="row in visibleRows" :key="row.uid" type="button" class="mail-row" :class="{ selected: message?.uid===row.uid, unread: row.unread }" @click="openMessage(row)"><span class="mail-row-from">{{ row.from }}</span><strong>{{ row.subject || tx("（无主题）","(no subject)") }}</strong><small>{{ row.date }}</small></button><p v-if="!loading && !visibleRows.length" class="mail-empty-list">{{ tx("此文件夹没有邮件。","No emails in this folder.") }}</p></div>
      <main class="mail-reader"><div v-if="message" class="mail-reader-content"><header class="mail-reader-head"><div><h2>{{ message.subject || tx("（无主题）","(no subject)") }}</h2><p><strong>{{ message.from }}</strong><br>{{ tx("收件人","To") }}: {{ message.to }}<span v-if="message.cc"><br>CC: {{ message.cc }}</span><br>{{ message.date }}</p></div><div class="mail-reader-actions"><button v-if="archiveFolder" type="button" :disabled="busy" :title="tx('归档','Archive')" @click="moveToArchive"><Archive :size="16" /></button><button type="button" :disabled="busy" :title="tx('标为已读/未读','Toggle read status')" @click="toggleRead">{{ selectedIsUnread ? tx("标为已读","Mark read") : tx("标为未读","Mark unread") }}</button><button type="button" :disabled="busy" :title="tx('删除','Delete')" @click="deleteMessage"><Trash2 :size="16" /></button><button type="button" :disabled="busy" @click="openCompose(true)"><Reply :size="15" /> {{ tx("回复","Reply") }}</button></div></header><div v-if="message.attachments.length" class="mail-attachments"><button v-for="attachment in message.attachments" :key="attachment.part" type="button" @click="downloadAttachment(attachment)"><Paperclip :size="14" /> {{ attachment.filename }}</button></div><pre class="mail-body">{{ message.body || tx("此邮件没有可显示的纯文本正文。","No plain text body is available for this email.") }}</pre></div><div v-else class="mail-reader-empty"><Mail :size="28" /><span>{{ tx("选择一封邮件查看内容","Select an email to read") }}</span></div></main>
    </section>
    <div v-if="composeOpen" class="compose-backdrop" @click.self="composeOpen=false"><form class="compose-card" @submit.prevent="sendMessage"><header><div><p class="compose-eyebrow">VERA · MAIL</p><h2>{{ tx("新邮件","New email") }}</h2></div><button type="button" :aria-label="tx('关闭','Close')" @click="composeOpen=false"><X :size="18" /></button></header>
      <label>{{ tx("邮件用途","Purpose") }}<select v-model="messagePurpose"><option value="existing_notice">{{ tx("现有客户业务通知（不含推广）","Existing customer service notice (non-promotional)") }}</option><option value="commercial_update">{{ tx("现有客户产品/价格推广","Product or price promotion to customers") }}</option><option value="first_contact">{{ tx("首次产品联系","First product outreach") }}</option></select></label>
      <section class="recipient-picker"><label><UserRound :size="15" /> {{ tx("从批发客户中筛选","Choose wholesale customers") }}<input v-model="customerSearch" :placeholder="tx('搜索公司、联系人或邮箱','Search company, contact or email')" /></label><div class="recipient-options"><label v-for="customer in visibleCustomers" :key="customer.customer_id" class="recipient-option"><input type="checkbox" :checked="selectedCustomerIds.includes(customer.customer_id)" @change="toggleCustomerRecipient(customer)" /><span><strong>{{ customer.company }}</strong><small>{{ customer.contact_name }} · {{ customer.email }}</small></span></label><p v-if="!visibleCustomers.length" class="mail-help">{{ tx('没有匹配的客户邮箱。也可以直接输入邮箱地址。','No matching customer emails. You can also enter email addresses manually.') }}</p></div></section>
      <label>{{ tx("收件人（可粘贴多个邮箱；会逐封发送）","To (paste multiple addresses; each receives a separate email)") }}<input v-model.trim="compose.to" placeholder="customer@example.com" required /></label>
      <label>CC<input v-model.trim="compose.cc" :placeholder="tx('单个收件人时可用','Available for one recipient')" /></label>
      <label v-if="preferences.templates.length">{{ tx("套用邮件模板","Email template") }}<select v-model="templateSelected" @change="loadTemplate(templateSelected)"><option value="">{{ tx('不套用模板','No template') }}</option><option v-for="template in preferences.templates" :key="template.id" :value="template.id">{{ template.name }}</option></select></label>
      <label>{{ tx("主题","Subject") }}<input v-model.trim="compose.subject" required maxlength="500" /></label><label>{{ tx("邮件内容","Message") }}<textarea v-model="compose.body" rows="9" required></textarea></label>
      <section v-if="messagePurpose !== 'existing_notice'" class="consent-check"><label><input v-model="consentConfirmed" type="checkbox" required />{{ tx("我已核实收件人同意接收此类商业邮件","I have verified recipient consent for this commercial email") }}</label><label>{{ tx("同意依据/来源","Consent basis/source") }}<input v-model.trim="consentSource" :placeholder="tx('例如：客户申请、网站勾选或相关业务公开邮箱','e.g. customer request, website opt-in or relevant published business address')" required /></label><small>{{ tx("商业邮件会附带退订说明，并逐个地址单独发送。","Commercial email includes an unsubscribe instruction and is sent separately to each address.") }}</small></section>
      <footer><span>{{ status?.email }} · {{ compose.to.split(/[,;\s]+/).filter(Boolean).length }} {{ tx('位收件人','recipient(s)') }}</span><button type="submit" class="mail-primary" :disabled="busy">{{ busy ? tx("发送中…","Sending…") : tx("逐封发送","Send individually") }}</button></footer></form></div>
    <div v-if="settingsOpen" class="compose-backdrop" @click.self="settingsOpen=false"><form class="compose-card mail-settings-card" @submit.prevent="saveMailPreferences"><header><div><p class="compose-eyebrow">VERA · BRAND VOICE</p><h2>{{ tx("邮件模板与签名","Email templates & signature") }}</h2></div><button type="button" :aria-label="tx('关闭','Close')" @click="settingsOpen=false"><X :size="18" /></button></header>
      <section class="template-editor"><h3>{{ tx("邮件模板","Email templates") }}</h3><div class="template-actions"><select v-model="templateSelected" @change="editTemplate(templateSelected)"><option value="">{{ tx('选择现有模板','Choose a template') }}</option><option v-for="template in preferences.templates" :key="template.id" :value="template.id">{{ template.name }}</option></select><button type="button" class="mail-icon-button" @click="templateSelected='';editTemplate()"><Plus :size="15" /> {{ tx('新模板','New template') }}</button></div><label>{{ tx("模板名称","Template name") }}<input v-model="templateDraft.name" required /></label><label>{{ tx("主题","Subject") }}<input v-model="templateDraft.subject" maxlength="500" /></label><label>{{ tx("正文","Message") }}<textarea v-model="templateDraft.body" rows="5"></textarea></label><button type="button" class="mail-icon-button" :disabled="busy || !templateDraft.name.trim()" @click="saveTemplate"><Save :size="15" /> {{ tx('保存模板','Save template') }}</button></section>
      <section class="signature-editor"><h3>{{ tx("发送签名","Signature") }}</h3><label>{{ tx("签名文字","Signature text") }}<textarea v-model="preferences.signature_text" rows="4" placeholder="Name · VERA Shading Solutions · Contact details"></textarea></label><input ref="imageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="readSignatureImage" /><button type="button" class="mail-icon-button" @click="imageInput?.click()"><ImagePlus :size="15" /> {{ tx('添加 Logo 图片','Add logo image') }}</button><img v-if="preferences.signature_image_data" class="signature-preview" :src="preferences.signature_image_data" alt="Email signature image preview" /><button type="submit" class="mail-primary" :disabled="busy">{{ busy ? tx('保存中…','Saving…') : tx('保存邮件设置','Save mail settings') }}</button></section>
    </form></div>
  </section>
</template>

<style scoped>
.mail-workspace{color:#344956}.mail-page-head .eyebrow{color:#6a7c88}.connected-pill{color:#607582}.mail-icon-button,.mail-reader-actions button,.compose-card header button{border-color:#d6e0e5;color:#405969}.mail-primary{border-color:#405969;background:#405969}.mail-notice{background:#e8f2f5;color:#355c70}.mail-connect-icon{background:#e8eef2;color:#405969}.mail-folder.active{background:#e4edf2;color:#344956}.mail-folder b{color:#405969}.compose-backdrop{background:#263945bb}.compose-card{width:min(740px,96vw);color:#304451}.compose-card input,.compose-card textarea,.compose-card select{border-color:#d3dfe5;color:#304451}.compose-eyebrow{margin:0 0 3px;color:#738792;font-size:9px;letter-spacing:.15em}.recipient-picker,.consent-check,.template-editor,.signature-editor{display:grid;gap:8px;padding:10px;border:1px solid #dce5e9;border-radius:8px;background:#f8fafb}.recipient-picker>label{display:flex;align-items:center;gap:6px}.recipient-options{display:grid;gap:2px;max-height:150px;overflow:auto}.recipient-option{display:grid!important;grid-template-columns:20px minmax(0,1fr);align-items:center;gap:8px!important;margin:0!important;padding:6px;border-bottom:1px solid #e5ecef}.recipient-option input,.consent-check input{width:16px!important;min-height:16px!important;margin:0!important;accent-color:#405969}.recipient-option span{display:grid;gap:1px;min-width:0}.recipient-option strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#344956}.recipient-option small{overflow:hidden;color:#71818a;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.consent-check label{display:grid;grid-template-columns:20px 1fr;align-items:center;gap:7px;margin:0}.consent-check small{color:#6f808b;font-size:10px}.compose-card footer span{color:#687b86}.mail-settings-card{width:min(680px,96vw)}.mail-settings-card h3{margin:0;font-size:14px}.template-actions{display:flex;gap:8px}.template-actions select{flex:1}.template-editor>label,.signature-editor>label{display:grid;gap:4px;color:#4d6470;font-size:11px;font-weight:700}.template-editor textarea,.signature-editor textarea{min-height:85px}.signature-preview{max-width:240px;max-height:90px;object-fit:contain;border:1px solid #dbe4e9;border-radius:5px;background:white;padding:5px}
.mail-workspace{display:flex;flex-direction:column;gap:12px;min-height:calc(100dvh - 135px);color:#344956}
.mail-page-head{display:flex;align-items:center;justify-content:space-between;gap:18px;padding:4px 0 12px;border-bottom:1px solid #d6e0e5}
.mail-page-head h1{margin:2px 0 3px;font-size:24px;line-height:1.2}
.mail-page-head>div:first-child>p:last-child{margin:0;color:#647782;font-size:13px}
.mail-head-actions{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.connected-pill{padding:7px 11px;border:1px solid #d7e1e6;border-radius:999px;background:#fff;font-size:12px}
.mail-icon-button,.mail-primary{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:0 13px;border:1px solid #bdcbd3;border-radius:999px;background:#fff;color:#405969;font:inherit;font-size:12px;font-weight:650;cursor:pointer}
.mail-icon-button:hover{background:#f0f4f6}
.mail-primary{border-color:#405969;background:#405969;color:#fff}
.mail-primary:hover{background:#324b5b}
.mail-icon-button:disabled,.mail-primary:disabled{opacity:.55;cursor:wait}
.mail-error,.mail-notice{margin:0;padding:10px 13px;border-radius:8px;font-size:13px}
.mail-error{background:#fff0ed;color:#8e382b}.mail-notice{background:#e8f2f5;color:#355c70}
.mail-client{display:grid;grid-template-columns:190px minmax(300px,360px) minmax(0,1fr);height:calc(100dvh - 235px);min-height:520px;max-height:820px;overflow:hidden;border:1px solid #d6e0e5;border-radius:12px;background:#fff;box-shadow:0 4px 18px #243c4b0a}
.mail-sidebar{display:flex;flex-direction:column;gap:4px;padding:12px 9px;border-right:1px solid #e1e8ec;background:#f7f9fa}
.mail-folder{display:flex;align-items:center;gap:10px;width:100%;min-height:40px;padding:0 11px;border:0;border-radius:999px;background:transparent;color:#4b606c;text-align:left;font:inherit;font-size:13px;cursor:pointer}
.mail-folder span{flex:1}.mail-folder:hover{background:#edf2f5}.mail-folder.active{background:#e4edf2;color:#344956;font-weight:700}.mail-folder b{font-size:11px}
.disconnect-link{margin:auto 8px 2px;padding:9px 0 2px;border:0;border-top:1px solid #dce5e9;background:transparent;color:#74838c;text-align:left;font:inherit;font-size:11px;cursor:pointer}
.mail-message-list{min-width:0;overflow:auto;border-right:1px solid #e1e8ec;background:#fff}
.mail-list-toolbar{position:sticky;top:0;z-index:2;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:8px;align-items:center;padding:14px 13px 12px;border-bottom:1px solid #e4eaee;background:#fff}
.mail-list-toolbar h2{grid-column:1/-1;margin:0;color:#344956;font-size:17px}
.mail-list-toolbar input{box-sizing:border-box;width:100%;min-width:0;height:36px;padding:0 11px;border:1px solid #d5dfe4;border-radius:999px;background:#f8fafb;color:#344956;font:inherit;font-size:12px}
.mail-list-toolbar>span{color:#71818a;font-size:11px;font-variant-numeric:tabular-nums}
.mail-row{position:relative;display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 10px;width:100%;min-height:76px;padding:13px 14px;border:0;border-bottom:1px solid #edf1f3;border-radius:0;background:#fff;color:#40515c;text-align:left;cursor:pointer}
.mail-row:hover{background:#f6f9fa}.mail-row.selected{background:#eaf1f5;box-shadow:inset 3px 0 #405969}.mail-row.unread .mail-row-from,.mail-row.unread strong{color:#293e4c;font-weight:750}
.mail-row-from{overflow:hidden;color:#4c606b;text-overflow:ellipsis;white-space:nowrap;font-size:12px}
.mail-row strong{grid-column:1/-1;overflow:hidden;color:#51636d;text-overflow:ellipsis;white-space:nowrap;font-size:12px;font-weight:550}
.mail-row small{grid-column:2;grid-row:1;color:#7c8b93;white-space:nowrap;font-size:10px}
.mail-empty-list{padding:22px 14px;color:#7a8991;font-size:12px}
.mail-reader{min-width:0;overflow:auto;background:#fff}
.mail-reader-content{padding:22px 26px}
.mail-reader-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px;padding-bottom:17px;border-bottom:1px solid #e4eaee}
.mail-reader-head h2{margin:0 0 11px;color:#2f424e;font-size:21px;line-height:1.35;overflow-wrap:anywhere}
.mail-reader-head p{margin:0;color:#708089;font-size:12px;line-height:1.7;overflow-wrap:anywhere}.mail-reader-head p strong{color:#40515c;font-size:13px}
.mail-reader-actions{display:flex;align-items:center;justify-content:flex-end;gap:6px;flex-wrap:wrap;flex:none}
.mail-reader-actions button{display:inline-flex;align-items:center;justify-content:center;gap:5px;min-height:34px;padding:0 9px;border:1px solid #d6e0e5;border-radius:999px;background:#fff;color:#405969;font:inherit;font-size:11px;cursor:pointer}
.mail-reader-actions button:hover{background:#f3f6f8}.mail-reader-actions button:disabled{opacity:.5}
.mail-attachments{display:flex;gap:8px;flex-wrap:wrap;padding:14px 0;border-bottom:1px solid #e9eef1}
.mail-attachments button{display:inline-flex;align-items:center;gap:6px;padding:7px 10px;border:1px solid #dce5e9;border-radius:999px;background:#f8fafb;color:#405969;font:inherit;font-size:11px;cursor:pointer}
.mail-body{margin:22px 0 0;color:#354852;font:13px/1.75 Arial,sans-serif;white-space:pre-wrap;overflow-wrap:anywhere}
.mail-reader-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:11px;height:100%;min-height:300px;color:#84929a;font-size:13px}
.mail-connect-card{align-self:center;width:min(520px,100%);margin:28px auto;padding:28px;border:1px solid #d6e0e5;border-radius:12px;background:#fff;box-shadow:0 8px 28px #243c4b0b}
.mail-connect-card h2{margin:12px 0 6px;color:#344956;font-size:20px}.mail-connect-card>p{color:#647782;font-size:13px;line-height:1.55}
.mail-connect-card form{display:grid;gap:12px;margin-top:18px}.mail-connect-card form label{display:grid;gap:5px;color:#425966;font-size:12px;font-weight:650}
.mail-connect-card input,.compose-card input,.compose-card textarea,.compose-card select{box-sizing:border-box;width:100%;min-height:38px;padding:8px 10px;border:1px solid #d3dfe5;border-radius:6px;background:#fff;color:#304451;font:inherit;font-size:13px}
.mail-connect-card form .mail-primary{width:max-content}.mail-help{margin:0;color:#73838c;font-size:11px;line-height:1.5}
.mail-key-notice{display:grid;gap:5px;margin:12px 0;padding:12px;border:1px solid #efd8ae;border-radius:8px;background:#fff9eb;color:#795b2d;font-size:12px}
.compose-backdrop{background:#263945bb}.compose-card{display:grid;gap:12px;box-sizing:border-box;width:min(740px,96vw);max-height:94dvh;overflow:auto;padding:19px;border:1px solid #d2dde3;border-radius:14px;background:#fff;color:#304451;box-shadow:0 22px 70px #182d3a55}
.compose-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid #e5ebee}
.compose-card>header h2{margin:0;color:#304451;font-size:20px}.compose-card>header button{display:grid;place-items:center;width:36px;height:36px;border:1px solid #d6e0e5;border-radius:50%;background:#fff;color:#405969;cursor:pointer}
.compose-card>label{display:grid;gap:5px;color:#425966;font-size:12px;font-weight:650}.compose-card textarea{resize:vertical;line-height:1.5}
.compose-card footer{position:sticky;bottom:-19px;display:flex;align-items:center;justify-content:space-between;gap:12px;margin:4px -19px -19px;padding:12px 19px;border-top:1px solid #e5ebee;background:#fff}.compose-card footer span{color:#687b86;font-size:11px}
.mail-settings-card{width:min(760px,96vw)}.template-editor,.signature-editor{gap:10px;padding:13px;border-color:#d8e2e7;background:#f8fafb}.mail-settings-card h3{margin:0;font-size:15px;color:#344956}
.template-editor>label,.signature-editor>label{font-size:12px;color:#425966}.template-editor textarea,.signature-editor textarea{min-height:92px}
.signature-preview{max-width:260px;max-height:100px}
@media(max-width:1050px){.mail-client{grid-template-columns:165px minmax(270px,330px) minmax(0,1fr)}.mail-reader-content{padding:18px}.mail-reader-head{display:grid}.mail-reader-actions{justify-content:flex-start}}
@media(max-width:760px){.mail-workspace{min-height:calc(100dvh - 110px)}.mail-page-head{align-items:flex-start;flex-direction:column}.mail-head-actions{width:100%;flex-wrap:wrap}.mail-client{height:auto;min-height:78dvh;grid-template-columns:118px minmax(0,1fr);grid-template-rows:minmax(270px,42dvh) minmax(340px,1fr)}.mail-sidebar{grid-column:1;grid-row:1/3;padding:9px 5px}.mail-folder{min-height:38px;padding:0 8px;font-size:11px}.mail-message-list{grid-column:2;grid-row:1;border-right:0;border-bottom:1px solid #e1e8ec}.mail-reader{grid-column:2;grid-row:2}.mail-reader-content{padding:14px}.mail-list-toolbar{padding:10px}.mail-list-toolbar input{width:100%}.mail-row{min-height:66px;padding:10px}.mail-connect-card{margin-top:10px;padding:18px}}
@media(max-width:900px){.mail-client{grid-template-columns:130px minmax(220px,35%) minmax(300px,1fr)}.mail-reader-head{display:grid}.mail-reader-actions{justify-content:flex-start}}
@media(max-width:760px){.mail-client{grid-template-columns:118px minmax(0,1fr)}}
</style>
