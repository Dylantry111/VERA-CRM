<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import { Mail, RefreshCw, PenLine, Archive, Trash2, Reply, Paperclip, X } from "lucide-vue-next";

const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
type MailStatus = { connected: boolean; credential_saved: boolean; credential_valid: boolean; email: string; provider: string; encryption_key_configured: boolean };
type MailFolder = { name: string; role: string };
type MailRow = { uid: string; from: string; to: string; subject: string; date: string; message_id: string; unread: boolean };
type MailAttachment = { part: number; filename: string; content_type: string };
type MailMessage = MailRow & { cc: string; in_reply_to: string; body: string; attachments: MailAttachment[] };
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
const composeOpen = ref(false);
const compose = reactive({ to: "", cc: "", subject: "", body: "", reply_to: "" });
const visibleRows = computed(() => {
  const term = search.value.trim().toLowerCase();
  return term ? rows.value.filter(row => `${row.from} ${row.subject} ${row.to}`.toLowerCase().includes(term)) : rows.value;
});
const unreadCount = computed(() => rows.value.filter(row => row.unread).length);
const archiveFolder = computed(() => folders.value.find(folder => folder.role === "archive" || /archive/i.test(folder.name))?.name || "");
const selectedIsUnread = computed(() => rows.value.find(row => row.uid === message.value?.uid)?.unread ?? false);

async function loadStatus() {
  error.value = "";
  try {
    status.value = await request<MailStatus>("operations/mailbox");
    if (status.value.connected) await loadFolders();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
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
  composeOpen.value = true;
}

async function sendMessage() {
  busy.value = true; error.value = ""; notice.value = "";
  try {
    await request("operations/mailbox/send", { ...compose });
    composeOpen.value = false;
    notice.value = tx("邮件已发送。","Email sent.");
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
    <header class="mail-page-head"><div><p class="eyebrow">VERA · COMMUNICATIONS</p><h1>{{ tx("邮件","Mail") }}</h1><p>{{ tx("在后台查看并管理企业邮箱。","View and manage your business mailbox from the admin workspace.") }}</p></div><div v-if="status?.connected" class="mail-head-actions"><span class="connected-pill">{{ status.email }}</span><button type="button" class="mail-icon-button" :disabled="loading" :aria-label="tx('刷新邮件','Refresh mail')" @click="loadMessages"><RefreshCw :size="16" /></button><button type="button" class="mail-primary" @click="openCompose()"><PenLine :size="15" /> {{ tx("写邮件","Compose") }}</button></div></header>
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
    <div v-if="composeOpen" class="compose-backdrop" @click.self="composeOpen=false"><form class="compose-card" @submit.prevent="sendMessage"><header><h2>{{ tx("新邮件","New email") }}</h2><button type="button" :aria-label="tx('关闭','Close')" @click="composeOpen=false"><X :size="18" /></button></header><label>{{ tx("收件人","To") }}<input v-model.trim="compose.to" placeholder="customer@example.com" required /></label><label>CC<input v-model.trim="compose.cc" /></label><label>{{ tx("主题","Subject") }}<input v-model.trim="compose.subject" required maxlength="500" /></label><textarea v-model="compose.body" rows="12" required></textarea><footer><span>{{ status?.email }}</span><button type="submit" class="mail-primary" :disabled="busy">{{ busy ? tx("发送中…","Sending…") : tx("发送","Send") }}</button></footer></form></div>
  </section>
</template>

<style scoped>
.mail-workspace{display:grid;gap:15px;min-height:calc(100dvh - 150px);color:#24372d}.mail-page-head{display:flex;align-items:center;justify-content:space-between;gap:18px}.mail-page-head .eyebrow{margin:0 0 4px;color:#668171;font-size:10px;font-weight:750;letter-spacing:.14em}.mail-page-head h1{margin:0;font-size:24px}.mail-page-head p:not(.eyebrow){margin:5px 0 0;color:#6c7a72;font-size:12px}.mail-head-actions{display:flex;align-items:center;gap:8px}.connected-pill{max-width:250px;overflow:hidden;text-overflow:ellipsis;color:#61746a;font-size:12px}.mail-icon-button,.mail-reader-actions button,.compose-card header button{display:inline-flex;align-items:center;justify-content:center;gap:6px;min-height:36px;padding:7px 10px;border:1px solid #d8e2da;border-radius:999px;background:#fff;color:#345744;cursor:pointer}.mail-primary{display:inline-flex;align-items:center;justify-content:center;gap:7px;min-height:38px;padding:8px 15px;border:1px solid #3d715c;border-radius:999px;background:#3d715c;color:white;font-size:12px;font-weight:700;cursor:pointer}.mail-primary:disabled,.mail-reader-actions button:disabled{opacity:.55;cursor:wait}.mail-error,.mail-notice{margin:0;padding:10px 13px;border-radius:7px;font-size:12px}.mail-error{background:#fff0ed;color:#8d3729}.mail-notice{background:#edf5ef;color:#286044}.mail-connect-card{width:min(520px,100%);box-sizing:border-box;align-self:start;justify-self:center;margin:auto;padding:25px;border:1px solid #dbe5dd;border-radius:12px;background:#fff;box-shadow:0 12px 35px #1a39200d}.mail-connect-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:50%;background:#eaf3ed;color:#37664d}.mail-connect-card h2{margin:14px 0 5px;font-size:19px}.mail-connect-card>p{margin:0 0 17px;color:#697a70;font-size:12px;line-height:1.55}.mail-connect-card form{display:grid;gap:11px}.mail-connect-card label,.compose-card label{display:grid;gap:5px;color:#4c6255;font-size:11px;font-weight:700}.mail-connect-card input,.compose-card input,.compose-card textarea{box-sizing:border-box;width:100%;min-height:38px;padding:8px 10px;border:1px solid #d2ddd4;border-radius:6px;background:#fff;color:#25392e;font:inherit;font-size:13px}.mail-key-notice{display:grid;gap:5px;margin:12px 0;padding:11px;border-radius:7px;background:#fff4df;color:#795515;font-size:11px;line-height:1.45}.mail-help{margin:0;color:#718078;font-size:10px;line-height:1.45}.mail-client{display:grid;grid-template-columns:155px minmax(250px,330px) minmax(300px,1fr);min-height:0;height:calc(100dvh - 205px);border:1px solid #dbe4dd;border-radius:10px;overflow:hidden;background:#fff}.mail-sidebar{display:flex;flex-direction:column;gap:4px;padding:12px 8px;border-right:1px solid #e6ece7;background:#f8faf8}.mail-folder{display:flex;align-items:center;gap:9px;width:100%;min-height:37px;padding:8px 10px;border:0;border-radius:999px;background:transparent;color:#566a5d;text-align:left;font-size:11px;cursor:pointer}.mail-folder span{flex:1}.mail-folder b{color:#3e7055;font-size:10px}.mail-folder.active{background:#e5efe8;color:#20573a;font-weight:700}.disconnect-link{margin-top:auto;padding:8px;border:0;background:none;color:#8a5148;text-align:left;font-size:10px;cursor:pointer}.mail-message-list{min-width:0;overflow:auto;border-right:1px solid #e6ece7}.mail-list-toolbar{position:sticky;top:0;z-index:1;display:flex;align-items:center;gap:8px;padding:10px;background:#fff;border-bottom:1px solid #e6ece7}.mail-list-toolbar h2{flex:1;min-width:0;margin:0;font-size:13px}.mail-list-toolbar input{width:130px;min-width:70px;height:30px;box-sizing:border-box;padding:5px 8px;border:1px solid #dce4dd;border-radius:999px;font-size:10px}.mail-list-toolbar>span{color:#758279;font-size:10px}.mail-row{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:5px 8px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #eff2ef;background:#fff;color:#32463a;text-align:left;cursor:pointer}.mail-row:hover,.mail-row.selected{background:#f1f6f2}.mail-row.unread strong,.mail-row.unread .mail-row-from{font-weight:750;color:#244a34}.mail-row-from{grid-column:1;overflow:hidden;color:#586d60;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.mail-row strong{grid-column:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.mail-row small{grid-column:2;grid-row:1/3;color:#849188;font-size:9px;white-space:nowrap}.mail-empty-list{padding:18px;color:#7b8980;font-size:11px;text-align:center}.mail-reader{min-width:0;overflow:auto}.mail-reader-content{padding:18px 21px}.mail-reader-head{display:flex;justify-content:space-between;gap:14px;padding-bottom:13px;border-bottom:1px solid #e7ece8}.mail-reader-head h2{margin:0 0 9px;font-size:17px;overflow-wrap:anywhere}.mail-reader-head p{margin:0;color:#64736a;font-size:10px;line-height:1.7;overflow-wrap:anywhere}.mail-reader-actions{display:flex;align-items:flex-start;flex-wrap:wrap;justify-content:flex-end;gap:5px}.mail-reader-actions button{min-height:31px;padding:5px 8px;font-size:10px;white-space:nowrap}.mail-attachments{display:flex;flex-wrap:wrap;gap:6px;margin:13px 0}.mail-attachments button{display:flex;align-items:center;gap:5px;padding:7px 9px;border:1px solid #dbe4dd;border-radius:999px;background:#f8faf8;color:#365943;font-size:10px;cursor:pointer}.mail-body{margin:16px 0;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 Arial,sans-serif;color:#34483a}.mail-reader-empty{display:grid;place-content:center;justify-items:center;gap:10px;height:100%;color:#86938b;font-size:12px}.compose-backdrop{position:fixed;inset:0;z-index:1100;display:grid;place-items:center;padding:15px;background:#15271dcc}.compose-card{display:grid;gap:11px;width:min(650px,96vw);max-height:92dvh;overflow:auto;padding:18px;border-radius:12px;background:#fff;box-shadow:0 20px 60px #06190e55}.compose-card header,.compose-card footer{display:flex;align-items:center;justify-content:space-between;gap:10px}.compose-card h2{margin:0;font-size:17px}.compose-card textarea{resize:vertical;min-height:180px}.compose-card footer span{overflow:hidden;color:#728078;text-overflow:ellipsis;font-size:10px}.compose-card footer .mail-primary{margin-left:auto}.compose-card header button{min-width:34px;min-height:34px;padding:6px}
@media(max-width:900px){.mail-client{grid-template-columns:130px minmax(220px,35%) minmax(300px,1fr)}.mail-reader-head{display:grid}.mail-reader-actions{justify-content:flex-start}}
@media(max-width:700px){.mail-workspace{min-height:calc(100dvh - 110px)}.mail-page-head{align-items:flex-start;flex-direction:column}.mail-head-actions{width:100%;flex-wrap:wrap}.mail-client{height:auto;min-height:75dvh;grid-template-columns:110px minmax(0,1fr);grid-template-rows:minmax(240px,45dvh) minmax(300px,1fr)}.mail-sidebar{grid-column:1;grid-row:1/3}.mail-message-list{grid-column:2;grid-row:1;border-right:0;border-bottom:1px solid #e6ece7}.mail-reader{grid-column:2;grid-row:2}.mail-reader-content{padding:13px}.mail-list-toolbar input{width:100px}.mail-connect-card{margin-top:10px;padding:18px}}
</style>
