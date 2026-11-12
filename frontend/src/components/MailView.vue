<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import { AlignCenter, AlignLeft, AlignRight, Mail, RefreshCw, PenLine, Archive, Trash2, Reply, Paperclip, X, Settings, Plus, UserRound, ImagePlus, Save } from "lucide-vue-next";

const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
type MailStatus = { connected: boolean; credential_saved: boolean; credential_valid: boolean; email: string; provider: string; encryption_key_configured: boolean };
type MailFolder = { name: string; role: string };
type MailRow = { uid: string; from: string; to: string; subject: string; date: string; message_id: string; unread: boolean };
type MailAttachment = { part: number; filename: string; content_type: string };
type ComposeAttachment = { file: File; filename: string; content_type: string; size: number };
type MailMessage = MailRow & { cc: string; in_reply_to: string; body: string; attachments: MailAttachment[] };
type MailTemplate = { id: string; name: string; subject: string; body: string };
type MailPreferences = { templates: MailTemplate[]; signature_text: string; signature_image_data: string; signature_html?: string | null };
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
const customerPickerOpen = ref(false);
const selectedCustomerIds = ref<number[]>([]);
const preferences = ref<MailPreferences>({ templates: [], signature_text: "", signature_image_data: "", signature_html: null });
const settingsOpen = ref(false);
const templateDraft = reactive({ id: "", name: "", subject: "", body: "" });
const templateSelected = ref("");
const imageInput = ref<HTMLInputElement | null>(null);
const signatureImageDraft = ref("");
const signatureHtmlDraft = ref("");
const signatureEditor = ref<HTMLDivElement | null>(null);
let signatureSelection: Range | null = null;
const signatureLogoWidthPx = ref(180);
const signatureLogoHeightPx = ref(0);
const signatureLockAspect = ref(true);
const signatureSelectedTarget = ref<"logo" | "brand" | "details">("logo");
const signatureTextColumnWidth = ref(62);
const signatureHorizontalAlign = ref("left");
const signatureVerticalAlign = ref("middle");
const hasSignatureColumns = computed(() => /<table\b/i.test(signatureHtmlDraft.value));
const messagePurpose = ref("existing_notice");
const consentConfirmed = ref(false);
const consentSource = ref("");
const composeOpen = ref(false);
const compose = reactive({ to: "", cc: "", subject: "", body: "", reply_to: "" });
const composeEditor = ref<HTMLDivElement | null>(null);
const composeHtmlDraft = ref("");
const composeAttachments = ref<ComposeAttachment[]>([]);
const composeAttachmentInput = ref<HTMLInputElement | null>(null);
const composeImageInput = ref<HTMLInputElement | null>(null);
const composeImageWidth = ref(420);
const composeImageAlign = ref("left");
const composeImageControlsOpen = ref(false);
let composeSelection: Range | null = null;
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
  catch { preferences.value = { templates: [], signature_text: "", signature_image_data: "", signature_html: null }; }
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
  void nextTick(() => {
    if (composeEditor.value) {
      composeEditor.value.innerHTML = composeContentHtml(template.body);
      updateComposeDraft();
    }
  });
}

function composeContentHtml(body: string) {
  const messageHtml = body.split(/\r?\n/).map(line => line ? `<p>${escapeHtml(line)}</p>` : "<p><br></p>").join("");
  const signature = preferences.value.signature_html != null ? preferences.value.signature_html : legacySignatureHtml();
  return `${messageHtml}${signature ? `<p><br></p><div style="max-width:720px;text-align:left;padding:12px 0 0;border-top:1px solid #d6e0e5">${signature}</div>` : ""}`;
}

function rememberComposeSelection() {
  const selection = window.getSelection();
  if (!selection?.rangeCount || !composeEditor.value) return;
  const range = selection.getRangeAt(0);
  if (composeEditor.value.contains(range.commonAncestorContainer)) composeSelection = range.cloneRange();
}

function restoreComposeSelection() {
  if (!composeEditor.value) return;
  composeEditor.value.focus();
  if (!composeSelection) return;
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(composeSelection);
}

function updateComposeDraft() {
  composeHtmlDraft.value = composeEditor.value?.innerHTML || "";
  compose.body = signatureTextFromHtml(composeHtmlDraft.value);
  rememberComposeSelection();
}

function formatCompose(command: string, value?: string) {
  restoreComposeSelection();
  document.execCommand("styleWithCSS", false, "true");
  document.execCommand(command, false, value);
  updateComposeDraft();
}

function applyComposeFont(event: Event) {
  formatCompose("fontName", (event.target as HTMLSelectElement).value);
}

function applyComposeFontSize(event: Event) {
  formatCompose("fontSize", (event.target as HTMLSelectElement).value);
}

function applyComposeBlock(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  formatCompose("formatBlock", value);
}

function applyComposeColor(event: Event) {
  formatCompose("foreColor", (event.target as HTMLInputElement).value);
}

function toggleComposeImageControls() {
  rememberComposeSelection();
  composeImageControlsOpen.value = !composeImageControlsOpen.value;
}

function chooseComposeImage() {
  rememberComposeSelection();
  composeImageInput.value?.click();
}

function insertComposeLink() {
  const href = window.prompt(tx("输入链接地址", "Enter link address"), "https://");
  if (!href) return;
  if (!/^(https?:\/\/|mailto:)/i.test(href.trim())) {
    error.value = tx("链接请使用 http、https 或 mailto 地址。", "Use an http, https or mailto link.");
    return;
  }
  formatCompose("createLink", href.trim());
}

function fileAsDataUrl(file: Blob) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error(tx("读取文件失败。", "Could not read the file.")));
    reader.readAsDataURL(file);
  });
}

async function optimizeComposeImage(file: File) {
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    throw new Error(tx("请选择不超过 5 MB 的 PNG、JPEG 或 WebP 图片。", "Choose a PNG, JPEG or WebP image under 5 MB."));
  }
  const bitmap = await createImageBitmap(file);
  const canvas = document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) throw new Error(tx("浏览器无法处理这张图片。", "This browser could not process the image."));
  let scale = Math.min(1, 1400 / bitmap.width, 1000 / bitmap.height);
  let quality = 0.9;
  let blob: Blob | null = null;
  for (let attempt = 0; attempt < 7; attempt++) {
    canvas.width = Math.max(1, Math.round(bitmap.width * scale));
    canvas.height = Math.max(1, Math.round(bitmap.height * scale));
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/webp", quality));
    if (blob?.type === "image/webp" && blob.size <= 450 * 1024) break;
    if (attempt % 2 === 1) scale *= 0.82;
    quality = Math.max(0.55, quality - 0.08);
  }
  bitmap.close();
  if (!blob || blob.type !== "image/webp" || blob.size > 700 * 1024) throw new Error(tx("图片压缩失败，请尝试更小的图片。", "Image optimization failed. Try a smaller image."));
  return fileAsDataUrl(new File([blob], "inline-image.webp", { type: "image/webp" }));
}

async function insertComposeImage(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  if (!file || !composeEditor.value) return;
  error.value = "";
  try {
    const dataUrl = await optimizeComposeImage(file);
    restoreComposeSelection();
    const width = Math.max(80, Math.min(900, Math.round(composeImageWidth.value)));
    const alignment = ["left", "center", "right"].includes(composeImageAlign.value) ? composeImageAlign.value : "left";
    document.execCommand("insertHTML", false, `<p style="text-align:${alignment}"><img src="${dataUrl}" alt="Inserted image" style="width:${width}px;max-width:100%;height:auto"></p>`);
    updateComposeDraft();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { input.value = ""; }
}

async function addComposeAttachments(event: Event) {
  const input = event.target as HTMLInputElement;
  const files = Array.from(input.files || []);
  if (!files.length) return;
  const maxTotal = 10 * 1024 * 1024;
  const existing = composeAttachments.value.reduce((sum, file) => sum + file.size, 0);
  const added = files.reduce((sum, file) => sum + file.size, 0);
  if (existing + added > maxTotal) {
    error.value = tx("附件总大小不能超过 10 MB。", "Attachments must total 10 MB or less.");
    input.value = "";
    return;
  }
  error.value = "";
  for (const file of files) composeAttachments.value.push({ file, filename: file.name, content_type: file.type || "application/octet-stream", size: file.size });
  input.value = "";
}

function removeComposeAttachment(index: number) {
  composeAttachments.value.splice(index, 1);
}

async function uploadComposeAttachments() {
  const uploads: { upload_id: string }[] = [];
  const chunkSize = 1024 * 1024;
  for (const [fileIndex, attachment] of composeAttachments.value.entries()) {
    notice.value = tx(`正在上传附件 ${fileIndex + 1}/${composeAttachments.value.length}…`, `Uploading attachment ${fileIndex + 1}/${composeAttachments.value.length}…`);
    const start = await request<{ upload_id: string }>("operations/mailbox/attachments/start", {
      filename: attachment.filename,
      content_type: attachment.content_type,
      size: attachment.size,
    });
    uploads.push({ upload_id: start.upload_id });
    const chunks = Math.ceil(attachment.size / chunkSize);
    for (let index = 0; index < chunks; index++) {
      const blob = attachment.file.slice(index * chunkSize, Math.min(attachment.size, (index + 1) * chunkSize));
      const dataUrl = await fileAsDataUrl(blob);
      await request("operations/mailbox/attachments/chunk", {
        upload_id: start.upload_id,
        index,
        data: dataUrl.split(",", 2)[1] || "",
      });
    }
  }
  notice.value = "";
  return uploads;
}

async function removeUploadedAttachments(uploads: { upload_id: string }[]) {
  await Promise.allSettled(uploads.map(({ upload_id }) => fetch(`/api/operations/mailbox/attachments/${upload_id}`, {
    method: "DELETE",
    headers: session.token ? { Authorization: `Bearer ${session.token}` } : {},
  })));
}

function editTemplate(id = "") {
  const template = preferences.value.templates.find(row => row.id === id);
  Object.assign(templateDraft, template || { id: crypto.randomUUID(), name: "", subject: "", body: "" });
}

async function saveTemplate() {
  if (!templateDraft.name.trim()) return;
  const next = { ...templateDraft, id: templateDraft.id || crypto.randomUUID() };
  const templates = [...preferences.value.templates];
  const existing = templates.findIndex(row => row.id === next.id);
  if (existing >= 0) templates.splice(existing, 1, next);
  else templates.push(next);
  await saveMailPreferences({ templates }, tx("邮件模板已保存。", "Email template saved."));
}

async function saveSignatureDesign() {
  if (!signatureEditor.value) return;
  const signatureHtml = sanitizeSignatureHtml(signatureEditor.value.innerHTML);
  signatureHtmlDraft.value = signatureHtml;
  const plainText = signatureTextFromHtml(signatureHtml);
  await saveMailPreferences({ signature_html: signatureHtml, signature_text: plainText }, tx("签名排版已保存。", "Signature design saved."));
  await nextTick();
  if (signatureEditor.value) signatureEditor.value.innerHTML = preferences.value.signature_html || "";
}

async function saveSignatureLogo() {
  await saveMailPreferences({ signature_image_data: signatureImageDraft.value }, tx("签名 Logo 已保存。", "Signature logo saved."));
}

async function saveMailPreferences(changes: Partial<MailPreferences>, successMessage: string) {
  busy.value = true; error.value = ""; notice.value = "";
  try {
    preferences.value = await request<MailPreferences>("operations/mailbox/preferences", changes);
    signatureImageDraft.value = preferences.value.signature_image_data;
    notice.value = successMessage;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}

function openMailSettings() {
  signatureImageDraft.value = preferences.value.signature_image_data;
  editTemplate(templateSelected.value);
  signatureHtmlDraft.value = preferences.value.signature_html != null ? preferences.value.signature_html : legacySignatureHtml();
  settingsOpen.value = true;
  void nextTick(() => {
    if (signatureEditor.value) {
      signatureEditor.value.innerHTML = signatureHtmlDraft.value;
      syncSignatureControls();
    }
  });
}

function syncSignatureControls() {
  const editor = signatureEditor.value;
  if (!editor) return;
  const image = editor.querySelector("img");
  if (image) {
    const width = Number.parseFloat(image.style.width);
    const height = Number.parseFloat(image.style.height);
    if (Number.isFinite(width) && width > 0) signatureLogoWidthPx.value = Math.round(width);
    if (Number.isFinite(height) && height > 0) signatureLogoHeightPx.value = Math.round(height);
    else if (image.naturalWidth > 0 && image.naturalHeight > 0) signatureLogoHeightPx.value = Math.round(signatureLogoWidthPx.value * image.naturalHeight / image.naturalWidth);
    signatureLockAspect.value = !Number.isFinite(height) || height <= 0 || image.style.height === "auto";
  }
  const cells = editor.querySelector("table")?.rows?.[0]?.cells;
  if (cells && cells.length >= 2) {
    const width = Number.parseFloat((cells[1] as HTMLElement).style.width);
    if (Number.isFinite(width) && width > 0) signatureTextColumnWidth.value = Math.round(width);
  }
}

function legacySignatureHtml() {
  const text = preferences.value.signature_text.split(/\r?\n/).map(line => line.trim() ? `<p>${escapeHtml(line)}</p>` : "<p><br></p>").join("");
  const image = preferences.value.signature_image_data ? `<p><img src="${preferences.value.signature_image_data}" alt="VERA Shading Solutions" style="max-width:180px;height:auto"></p>` : "";
  return `${text}${image}`;
}

function signatureTextFromHtml(markup: string) {
  const document = new DOMParser().parseFromString(markup, "text/html");
  return (document.body.innerText || document.body.textContent || "").replace(/\n{3,}/g, "\n\n").trim();
}

function sanitizeSignatureHtml(markup: string) {
  const document = new DOMParser().parseFromString(markup, "text/html");
  const allowed = new Set(["P", "DIV", "BR", "SPAN", "STRONG", "B", "EM", "I", "U", "FONT", "A", "IMG", "UL", "OL", "LI", "H2", "H3", "BLOCKQUOTE", "TABLE", "TBODY", "TR", "TD"]);
  for (const element of [...document.body.querySelectorAll("*")]) {
    if (!allowed.has(element.tagName)) { element.replaceWith(...element.childNodes); continue; }
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name === "style") {
        const styles = value.split(";").map(part => part.split(/:(.*)/s)).filter(parts => parts.length > 1).flatMap(([property, raw]) => {
          const key = property.trim().toLowerCase(); const item = raw.trim();
          const permitted = key === "font-family" ? /^[\w ,"'-]{1,90}$/.test(item)
            : key === "font-size" ? /^\d{1,3}(?:px|pt|em|rem|%)$/.test(item)
            : key === "color" || key === "background-color" ? /^(?:#[\da-f]{3,8}|[a-z]{1,24}|rgba?\([\d.,% ]+\))$/i.test(item)
            : key === "text-align" ? /^(left|center|right|justify)$/.test(item)
            : key === "font-weight" ? /^(normal|bold|[1-9]00)$/.test(item)
            : key === "font-style" ? /^(normal|italic|oblique)$/.test(item)
            : key === "text-decoration" ? /^(none|underline|line-through)$/.test(item)
            : ["width", "max-width", "height", "vertical-align", "padding", "padding-left", "padding-right"].includes(key) && /^[\w.% -]{1,32}$/.test(item);
          return permitted ? [`${key}:${item}`] : [];
        });
        if (styles.length) element.setAttribute("style", styles.join(";")); else element.removeAttribute("style");
      } else if (element.tagName === "IMG" && name === "src" && /^data:image\/(?:png|jpeg|webp);base64,[a-z0-9+/=]+$/i.test(value)) {
        element.setAttribute("src", value);
      } else if (element.tagName === "A" && name === "href" && /^(?:https?:|mailto:)/i.test(value)) {
        element.setAttribute("href", value);
      } else if ((element.tagName === "IMG" && name === "alt") || (element.tagName === "FONT" && ["face", "size", "color"].includes(name))) {
        if (name !== "size" || /^[1-7]$/.test(value)) element.setAttribute(name, value);
        else element.removeAttribute(name);
      } else if ((element.tagName === "TD" || element.tagName === "TABLE") && ["colspan", "rowspan", "width"].includes(name) && /^\d{1,3}$/.test(value)) {
        element.setAttribute(name, value);
      } else element.removeAttribute(name);
    }
    if (element.tagName === "IMG" && !element.hasAttribute("src")) element.remove();
  }
  return document.body.innerHTML;
}

function rememberSignatureSelection() {
  const selection = window.getSelection();
  if (!selection?.rangeCount || !signatureEditor.value) return;
  const range = selection.getRangeAt(0);
  if (signatureEditor.value.contains(range.commonAncestorContainer)) signatureSelection = range.cloneRange();
}

function restoreSignatureSelection() {
  if (!signatureEditor.value) return;
  signatureEditor.value.focus();
  if (!signatureSelection) return;
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(signatureSelection);
}

function formatSignature(command: string, value?: string) {
  restoreSignatureSelection();
  document.execCommand("styleWithCSS", false, "true");
  document.execCommand(command, false, value);
  signatureHtmlDraft.value = signatureEditor.value?.innerHTML || "";
  rememberSignatureSelection();
}

function applySignatureFont(event: Event) {
  formatSignature("fontName", (event.target as HTMLSelectElement).value);
}

function applySignatureSize(event: Event) {
  formatSignature("fontSize", (event.target as HTMLSelectElement).value);
}

function applySignatureColor(event: Event) {
  formatSignature("foreColor", (event.target as HTMLInputElement).value);
}

function selectSignatureTarget(event: MouseEvent) {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const editor = signatureEditor.value;
  if (!editor) return;
  const image = target instanceof HTMLImageElement ? target : target.closest("img");
  if (image instanceof HTMLImageElement) {
    signatureSelectedTarget.value = "logo";
    const parsedWidth = Number.parseFloat(image.style.width);
    signatureLogoWidthPx.value = Number.isFinite(parsedWidth) && parsedWidth > 0 ? Math.round(parsedWidth) : 180;
    const parsedHeight = Number.parseFloat(image.style.height);
    signatureLogoHeightPx.value = Number.isFinite(parsedHeight) && parsedHeight > 0 ? Math.round(parsedHeight) : Math.round(signatureLogoWidthPx.value * (image.naturalHeight / Math.max(1, image.naturalWidth)));
    signatureLockAspect.value = !Number.isFinite(parsedHeight) || parsedHeight <= 0 || image.style.height === "auto";
  } else {
    const cell = target.closest("td");
    if (cell) {
      const cells = Array.from(cell.parentElement?.children || []);
      signatureSelectedTarget.value = cells.indexOf(cell) === 0 ? "brand" : "details";
      const parsedWidth = Number.parseFloat((cell as HTMLElement).style.width);
      if (Number.isFinite(parsedWidth)) signatureTextColumnWidth.value = signatureSelectedTarget.value === "details" ? Math.round(parsedWidth) : 100 - Math.round(parsedWidth);
      signatureHorizontalAlign.value = (cell as HTMLElement).style.textAlign || "left";
      signatureVerticalAlign.value = (cell as HTMLElement).style.verticalAlign || "middle";
    }
  }
  rememberSignatureSelection();
}

function applySignatureLogoDimensions(field: "width" | "height" = "width") {
  const editor = signatureEditor.value;
  if (!editor) return;
  const image = editor.querySelector("img");
  if (!image) {
    error.value = tx("请先插入 Logo。", "Insert a logo first.");
    return;
  }
  const ratio = image.naturalWidth > 0 && image.naturalHeight > 0
    ? image.naturalWidth / image.naturalHeight
    : signatureLogoWidthPx.value / Math.max(1, signatureLogoHeightPx.value || 1);
  if (field === "height" && signatureLockAspect.value) {
    signatureLogoWidthPx.value = Math.max(1, Math.round(signatureLogoHeightPx.value * ratio));
  } else if (field === "width" && signatureLockAspect.value) {
    signatureLogoHeightPx.value = Math.max(1, Math.round(signatureLogoWidthPx.value / ratio));
  }
  image.style.width = `${Math.max(1, signatureLogoWidthPx.value)}px`;
  image.style.maxWidth = "100%";
  image.style.height = signatureLockAspect.value ? "auto" : `${Math.max(1, signatureLogoHeightPx.value)}px`;
  signatureHtmlDraft.value = editor.innerHTML;
}

function applySignatureColumnWidth() {
  const editor = signatureEditor.value;
  const cells = editor?.querySelector("table")?.rows?.[0]?.cells;
  if (!cells || cells.length < 2) {
    error.value = tx("请先添加左右布局。", "Add a side-by-side layout first.");
    return;
  }
  const selectedWidth = Math.max(10, Math.min(90, Math.round(signatureTextColumnWidth.value)));
  signatureTextColumnWidth.value = selectedWidth;
  cells[0].style.width = `${100 - selectedWidth}%`;
  cells[1].style.width = `${selectedWidth}%`;
  signatureHtmlDraft.value = editor.innerHTML;
}

function applySignatureAlignment() {
  const editor = signatureEditor.value;
  if (!editor) return;
  const image = editor.querySelector("img");
  const cells = editor.querySelector("table")?.rows?.[0]?.cells;
  const selectedCell = cells?.[signatureSelectedTarget.value === "brand" ? 0 : 1];
  if (signatureSelectedTarget.value === "logo" && image) {
    const brandCell = image.closest("td") as HTMLElement | null;
    if (brandCell) {
      brandCell.style.textAlign = signatureHorizontalAlign.value;
      brandCell.style.verticalAlign = signatureVerticalAlign.value;
    }
  } else if (selectedCell) {
    (selectedCell as HTMLElement).style.textAlign = signatureHorizontalAlign.value;
    (selectedCell as HTMLElement).style.verticalAlign = signatureVerticalAlign.value;
  }
  signatureHtmlDraft.value = editor.innerHTML;
}

function insertSignatureLogo() {
  const logo = signatureImageDraft.value || preferences.value.signature_image_data;
  if (!logo) {
    error.value = tx("请先在上方上传并保存 Logo。", "Upload and save the logo above first.");
    return;
  }
  restoreSignatureSelection();
  document.execCommand("insertHTML", false, `<img src="${logo}" alt="VERA Shading Solutions" style="width:${signatureLogoWidthPx.value}px;max-width:100%;height:auto;vertical-align:middle">`);
  signatureHtmlDraft.value = signatureEditor.value?.innerHTML || "";
  rememberSignatureSelection();
}

function arrangeSignatureSideBySide() {
  const editor = signatureEditor.value;
  if (!editor) return;
  if (editor.querySelector("table")) {
    error.value = tx("签名已经是左右布局，可以直接编辑两侧内容。", "This signature already uses a side-by-side layout. Edit either column directly.");
    return;
  }

  const existingLogo = editor.querySelector("img");
  const logoParagraph = existingLogo?.closest("p, div") || null;
  const nodes = Array.from(editor.childNodes);
  const tagline = nodes.find(node => (node.textContent || "").trim().toLowerCase() === "made for trade. built on trust.");

  const table = document.createElement("table");
  table.dataset.signatureLayout = "columns";
  table.setAttribute("width", "100%");
  table.style.width = "100%";
  table.style.borderCollapse = "collapse";
  table.style.fontFamily = "Arial, sans-serif";
  const body = document.createElement("tbody");
  const row = document.createElement("tr");
  const brandCell = document.createElement("td");
  brandCell.style.width = "32%";
  brandCell.style.paddingRight = "18px";
  brandCell.style.verticalAlign = "middle";
  brandCell.style.textAlign = "center";
  const detailsCell = document.createElement("td");
  detailsCell.style.width = "68%";
  detailsCell.style.paddingLeft = "18px";
  detailsCell.style.verticalAlign = "middle";

  if (existingLogo) {
    const logo = existingLogo.cloneNode(true) as HTMLImageElement;
    logo.style.display = "block";
    logo.style.maxWidth = "100%";
    logo.style.height = "auto";
    brandCell.append(logo);
  } else {
    const placeholder = document.createElement("p");
    placeholder.textContent = tx("在这里放置 Logo", "Place your logo here");
    brandCell.append(placeholder);
  }
  if (tagline) brandCell.append(tagline.cloneNode(true));

  for (const node of nodes) {
    if (node === tagline) continue;
    const content = node.cloneNode(true);
    if (content.nodeType === Node.ELEMENT_NODE) {
      const element = content as HTMLElement;
      if (node === logoParagraph) element.querySelectorAll("img").forEach(image => image.remove());
      if ((element.textContent || "").trim() || element.querySelector("img,br,table")) detailsCell.append(element);
    } else if ((content.textContent || "").trim()) {
      detailsCell.append(content);
    }
  }
  if (!detailsCell.childNodes.length) {
    const placeholder = document.createElement("p");
    placeholder.innerHTML = "<br>";
    detailsCell.append(placeholder);
  }

  row.append(brandCell, detailsCell);
  body.append(row);
  table.append(body);
  editor.replaceChildren(table);

  const range = document.createRange();
  range.selectNodeContents(brandCell);
  range.collapse(false);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
  signatureSelection = range.cloneRange();
  signatureHtmlDraft.value = editor.innerHTML;
}

function updateSignatureDraft() {
  signatureHtmlDraft.value = signatureEditor.value?.innerHTML || "";
  rememberSignatureSelection();
}

async function readSignatureImage(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0];
  if (!file) return;
  if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
    error.value = tx("请使用不超过 5 MB 的 PNG、JPEG 或 WebP 图片。", "Choose a PNG, JPEG or WebP image under 5 MB.");
    return;
  }
  error.value = "";
  try {
    const bitmap = await createImageBitmap(file);
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Image optimization is not available in this browser.");
    let scale = Math.min(1, 1400 / bitmap.width, 900 / bitmap.height);
    let quality = 0.9;
    let blob: Blob | null = null;
    for (let attempt = 0; attempt < 7; attempt++) {
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      context.clearRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/webp", quality));
      if (blob && blob.type === "image/webp" && blob.size <= 450 * 1024) break;
      if (attempt % 2 === 1) scale *= 0.82;
      quality = Math.max(0.55, quality - 0.08);
    }
    bitmap.close();
    if (!blob || blob.type !== "image/webp" || blob.size > 700 * 1024) {
      throw new Error(tx("图片无法压缩到邮件签名可用的大小，请尝试更小的图片。", "This image could not be optimized for an email signature. Try a smaller image."));
    }
    const reader = new FileReader();
    reader.onload = () => { signatureImageDraft.value = String(reader.result || ""); };
    reader.onerror = () => { error.value = tx("读取图片失败，请重试。", "Could not read the image. Please try again."); };
    reader.readAsDataURL(blob);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : tx("图片处理失败，请重试。", "Image processing failed. Please try again.");
  }
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

async function openCompose(reply = false) {
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
  composeAttachments.value = [];
  composeHtmlDraft.value = "";
  composeImageControlsOpen.value = false;
  await nextTick();
  if (composeEditor.value) {
    composeEditor.value.innerHTML = composeContentHtml(compose.body);
    updateComposeDraft();
  }
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
    const editorHtml = sanitizeSignatureHtml(composeEditor.value?.innerHTML || composeHtmlDraft.value);
    const plainBody = signatureTextFromHtml(editorHtml);
    if (!plainBody && !/<img\b/i.test(editorHtml)) throw new Error(tx("请填写邮件内容。", "Enter a message before sending."));
    const htmlBody = `<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.6;color:#304451\">${editorHtml}${unsubscribe}</div>`;
    const uploadedAttachments = await uploadComposeAttachments();
    let sentCount = 0;
    for (const recipient of recipients) {
      await request("operations/mailbox/send", { ...compose, body: plainBody || "[Inline image]", to: recipient, cc: recipients.length > 1 ? "" : compose.cc, html_body: htmlBody, attachments: uploadedAttachments, purpose: messagePurpose.value, consent_confirmed: consentConfirmed.value, consent_source: consentSource.value.trim() });
      sentCount++;
    }
    await removeUploadedAttachments(uploadedAttachments);
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
    <header class="mail-page-head"><div><p class="eyebrow">VERA · COMMUNICATIONS</p><h1>{{ tx("邮件","Mail") }}</h1><p>{{ tx("在后台查看并管理企业邮箱。","View and manage your business mailbox from the admin workspace.") }}</p></div><div v-if="status?.connected" class="mail-head-actions"><span class="connected-pill">{{ status.email }}</span><button type="button" class="mail-icon-button" :disabled="loading" :aria-label="tx('刷新邮件','Refresh mail')" @click="loadMessages"><RefreshCw :size="16" /></button><button type="button" class="mail-icon-button" :aria-label="tx('邮件模板与签名设置','Email template and signature settings')" @click="openMailSettings"><Settings :size="16" /> {{ tx('邮件设置','Mail settings') }}</button><button type="button" class="mail-primary" @click="openCompose()"><PenLine :size="15" /> {{ tx("写邮件","Compose") }}</button></div></header>
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
    <div v-if="composeOpen" class="compose-backdrop compose-backdrop-full" @click.self="composeOpen=false"><form class="compose-card mail-compose-card" @submit.prevent="sendMessage"><header class="compose-header-inline"><div class="compose-title"><p class="compose-eyebrow">VERA · MAIL</p><h2>{{ tx("新邮件","New email") }}</h2></div><div class="compose-head-fields" :class="{ single: !preferences.templates.length }"><label>{{ tx("邮件用途","Purpose") }}<select v-model="messagePurpose"><option value="existing_notice">{{ tx("现有客户业务通知（不含推广）","Existing customer service notice (non-promotional)") }}</option><option value="commercial_update">{{ tx("现有客户产品/价格推广","Product or price promotion to customers") }}</option><option value="first_contact">{{ tx("首次产品联系","First product outreach") }}</option></select></label><label v-if="preferences.templates.length">{{ tx("邮件模板","Template") }}<select v-model="templateSelected" @change="loadTemplate(templateSelected)"><option value="">{{ tx('不套用模板','No template') }}</option><option v-for="template in preferences.templates" :key="template.id" :value="template.id">{{ template.name }}</option></select></label></div><button type="button" :aria-label="tx('关闭','Close')" @click="composeOpen=false"><X :size="18" /></button></header>
      <div v-if="customerPickerOpen" class="customer-picker-backdrop" @click.self="customerPickerOpen=false"><section class="customer-picker-card" role="dialog" aria-modal="true" :aria-label="tx('选择邮件收件人','Choose email recipients')"><header><div><h3>{{ tx("选择批发客户","Choose wholesale customers") }}</h3><p>{{ tx("选择后会自动填入收件人，可继续多选。","Selected addresses are added to the recipient field; you can choose multiple customers.") }}</p></div><button type="button" :aria-label="tx('关闭','Close')" @click="customerPickerOpen=false"><X :size="17" /></button></header><input v-model="customerSearch" :placeholder="tx('搜索公司、联系人或邮箱','Search company, contact or email')" /><div class="customer-picker-options"><label v-for="customer in visibleCustomers" :key="customer.customer_id" class="recipient-option"><input type="checkbox" :checked="selectedCustomerIds.includes(customer.customer_id)" @change="toggleCustomerRecipient(customer)" /><span><strong>{{ customer.company }}</strong><small>{{ customer.contact_name }} · {{ customer.email }}</small></span></label><p v-if="!visibleCustomers.length" class="mail-help">{{ tx('没有匹配的客户邮箱。也可以直接输入邮箱地址。','No matching customer emails. You can also enter email addresses manually.') }}</p></div><footer><span>{{ selectedCustomerIds.length }} {{ tx('位客户已选','selected') }}</span><button type="button" class="mail-primary" @click="customerPickerOpen=false">{{ tx("完成","Done") }}</button></footer></section></div>
      <div class="compose-address-grid"><button type="button" class="customer-picker-trigger" @click="customerPickerOpen=true"><UserRound :size="15" /> {{ tx("客户","Customers") }}<span v-if="selectedCustomerIds.length">{{ selectedCustomerIds.length }}</span></button><label>{{ tx("收件人（逐封发送）","To (sent separately)") }}<input v-model.trim="compose.to" placeholder="customer@example.com" required /></label><label>CC<input v-model.trim="compose.cc" :placeholder="tx('单个收件人时可用','For one recipient')" /></label><label>{{ tx("主题","Subject") }}<input v-model.trim="compose.subject" required maxlength="500" /></label></div>
      <div class="compose-editor-shell"><div class="compose-toolbar" role="toolbar" :aria-label="tx('邮件格式工具栏','Email formatting toolbar')"><select aria-label="Font family" title="Font family" @mousedown="rememberComposeSelection" @change="applyComposeFont"><option value="Arial">Arial</option><option value="Georgia">Georgia</option><option value="Verdana">Verdana</option><option value="Tahoma">Tahoma</option><option value="Times New Roman">Times New Roman</option></select><select aria-label="Font size" title="Font size" @mousedown="rememberComposeSelection" @change="applyComposeFontSize"><option value="1">10 px</option><option value="2">13 px</option><option value="3" selected>16 px</option><option value="4">18 px</option><option value="5">24 px</option><option value="6">32 px</option><option value="7">48 px</option></select><select aria-label="Paragraph style" title="Paragraph style" @mousedown="rememberComposeSelection" @change="applyComposeBlock"><option value="<p>">Paragraph</option><option value="<h2>">Heading</option><option value="<h3>">Subheading</option><option value="<blockquote>">Quote</option></select><button type="button" title="Bold" aria-label="Bold" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('bold')"><strong>B</strong></button><button type="button" title="Italic" aria-label="Italic" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('italic')"><em>I</em></button><button type="button" title="Underline" aria-label="Underline" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('underline')"><u>U</u></button><input type="color" aria-label="Text color" title="Text color" value="#304451" @mousedown="rememberComposeSelection" @input="applyComposeColor" /><button type="button" title="Bulleted list" aria-label="Bulleted list" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('insertUnorderedList')">• {{ tx('列表','List') }}</button><button type="button" title="Numbered list" aria-label="Numbered list" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('insertOrderedList')">1.</button><button type="button" title="Align left" aria-label="Align left" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('justifyLeft')"><AlignLeft :size="15" /></button><button type="button" title="Align center" aria-label="Align center" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('justifyCenter')"><AlignCenter :size="15" /></button><button type="button" title="Align right" aria-label="Align right" @mousedown.prevent="rememberComposeSelection" @click="formatCompose('justifyRight')"><AlignRight :size="15" /></button><button type="button" @mousedown.prevent="rememberComposeSelection" @click="insertComposeLink">{{ tx('插入链接','Link') }}</button><button type="button" :class="{ active: composeImageControlsOpen }" @mousedown.prevent="rememberComposeSelection" @click="toggleComposeImageControls"><ImagePlus :size="14" /> {{ tx('图片','Image') }}</button><button type="button" @click="composeAttachmentInput?.click()"><Paperclip :size="14" /> {{ tx('附件','Attach') }}</button><small class="compose-attachment-limit">{{ tx('附件上限 10 MB','10 MB total limit') }}</small></div>
        <div v-if="composeImageControlsOpen" class="compose-image-controls"><label>{{ tx('图片宽度 px','Image width px') }}<input v-model.number="composeImageWidth" type="number" min="80" max="900" /></label><label>{{ tx('图片位置','Image alignment') }}<select v-model="composeImageAlign"><option value="left">{{ tx('左','Left') }}</option><option value="center">{{ tx('居中','Center') }}</option><option value="right">{{ tx('右','Right') }}</option></select></label><button type="button" @mousedown.prevent="rememberComposeSelection" @click="chooseComposeImage"><ImagePlus :size="14" /> {{ tx('选择图片','Choose image') }}</button><input ref="composeImageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="insertComposeImage" /></div>
        <input ref="composeAttachmentInput" type="file" multiple hidden @change="addComposeAttachments" />
        <div ref="composeEditor" class="compose-editor-canvas" contenteditable="true" role="textbox" aria-multiline="true" :aria-label="tx('邮件正文编辑区','Email body editor')" @input="updateComposeDraft" @mouseup="rememberComposeSelection" @keyup="rememberComposeSelection"></div><div class="compose-editor-hint">{{ tx('签名已显示在正文中，可在发送前编辑。','Your signature is shown in the message and can be edited before sending.') }}</div>
      </div>
      <div v-if="composeAttachments.length" class="compose-attachment-list"><span v-for="(file,index) in composeAttachments" :key="`${file.filename}-${index}`"><Paperclip :size="13" />{{ file.filename }} · {{ (file.size/1024).toFixed(0) }} KB<button type="button" :aria-label="tx('移除附件','Remove attachment')" @click="removeComposeAttachment(index)"><X :size="13" /></button></span><small>{{ tx('附件合计','Total attachments') }} {{ (composeAttachments.reduce((sum,file)=>sum+file.size,0)/1024/1024).toFixed(2) }} / 10 MB</small></div>
      <section v-if="messagePurpose !== 'existing_notice'" class="consent-check"><label><input v-model="consentConfirmed" type="checkbox" required />{{ tx("我已核实收件人同意接收此类商业邮件","I have verified recipient consent for this commercial email") }}</label><label>{{ tx("同意依据/来源","Consent basis/source") }}<input v-model.trim="consentSource" :placeholder="tx('例如：客户申请、网站勾选或相关业务公开邮箱','e.g. customer request, website opt-in or relevant published business address')" required /></label><small>{{ tx("商业邮件会附带退订说明，并逐个地址单独发送。","Commercial email includes an unsubscribe instruction and is sent separately to each address.") }}</small></section>
      <footer><span>{{ status?.email }} · {{ compose.to.split(/[,;\s]+/).filter(Boolean).length }} {{ tx('位收件人','recipient(s)') }}</span><button type="submit" class="mail-primary" :disabled="busy">{{ busy ? (composeAttachments.length ? tx("上传并发送中…","Uploading and sending…") : tx("发送中…","Sending…")) : tx("逐封发送","Send individually") }}</button></footer></form></div>
    <div v-if="settingsOpen" class="compose-backdrop" @click.self="settingsOpen=false"><section class="compose-card mail-settings-card" role="dialog" aria-modal="true" :aria-label="tx('邮件设置','Mail settings')"><header><div><p class="compose-eyebrow">VERA · BRAND VOICE</p><h2>{{ tx("邮件设置","Mail settings") }}</h2></div><button type="button" :aria-label="tx('关闭','Close')" @click="settingsOpen=false"><X :size="18" /></button></header>
      <form class="template-editor" @submit.prevent="saveTemplate"><h3>{{ tx("邮件模板","Email templates") }}</h3><div class="template-actions"><select v-model="templateSelected" @change="editTemplate(templateSelected)"><option value="">{{ tx('选择现有模板','Choose a template') }}</option><option v-for="template in preferences.templates" :key="template.id" :value="template.id">{{ template.name }}</option></select><button type="button" class="mail-icon-button" @click="templateSelected='';editTemplate()"><Plus :size="15" /> {{ tx('新模板','New template') }}</button></div><label>{{ tx("模板名称","Template name") }}<input v-model="templateDraft.name" required /></label><label>{{ tx("主题","Subject") }}<input v-model="templateDraft.subject" maxlength="500" /></label><label>{{ tx("正文","Message") }}<textarea v-model="templateDraft.body" rows="5"></textarea></label><button type="submit" class="mail-primary" :disabled="busy || !templateDraft.name.trim()"><Save :size="15" /> {{ tx('保存模板','Save template') }}</button></form>
      <section class="signature-logo-editor"><h3>{{ tx("签名 Logo","Signature logo") }}</h3><p>{{ tx("可上传不超过 5 MB 的 PNG、JPEG 或 WebP 图片；系统会自动优化图片尺寸，便于邮件使用。","Upload a PNG, JPEG or WebP image up to 5 MB. The image is optimized automatically for email.") }}</p><input ref="imageInput" type="file" accept="image/png,image/jpeg,image/webp" hidden @change="readSignatureImage" /><div class="signature-logo-actions"><button type="button" class="mail-icon-button" @click="imageInput?.click()"><ImagePlus :size="15" /> {{ tx('上传 Logo','Upload logo') }}</button><button v-if="signatureImageDraft" type="button" class="mail-icon-button" @click="signatureImageDraft=''">{{ tx('移除 Logo','Remove logo') }}</button></div><img v-if="signatureImageDraft" class="signature-preview" :src="signatureImageDraft" alt="Email signature logo preview" /><p v-else class="mail-help">{{ tx("尚未设置 Logo。","No logo is set yet.") }}</p><button type="button" class="mail-primary" :disabled="busy" @click="saveSignatureLogo">{{ busy ? tx('保存中…','Saving…') : tx('保存 Logo','Save logo') }}</button></section>
      <form class="signature-editor" @submit.prevent="saveSignatureDesign"><h3>{{ tx("签名设计","Signature design") }}</h3><p class="signature-editor-help">{{ tx("在下方直接编辑签名。选择文字后可调整格式；“左右布局”会将现有 Logo 自动放到左栏，其余内容放到右栏。点击 Logo 或栏位后，可在下方输入尺寸并调整对齐。","Edit your signature below. Format selected text; “Side-by-side” places the existing logo on the left and the remaining content on the right. Select the logo or a column to adjust its size and alignment below.") }}</p><div class="signature-design-grid"><div class="signature-editor-workspace"><div class="signature-toolbar" role="toolbar" :aria-label="tx('签名格式工具栏','Signature formatting toolbar')"><select aria-label="Font family" title="Font family" @mousedown="rememberSignatureSelection" @change="applySignatureFont"><option value="Arial">Arial</option><option value="Georgia">Georgia</option><option value="Verdana">Verdana</option><option value="Tahoma">Tahoma</option><option value="Times New Roman">Times New Roman</option></select><select aria-label="Font size" title="Font size" @mousedown="rememberSignatureSelection" @change="applySignatureSize"><option value="1">10 px</option><option value="2">13 px</option><option value="3" selected>16 px</option><option value="4">18 px</option><option value="5">24 px</option><option value="6">32 px</option><option value="7">48 px</option></select><button type="button" class="format-button" title="Bold" aria-label="Bold" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('bold')"><strong>B</strong></button><button type="button" class="format-button italic" title="Italic" aria-label="Italic" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('italic')">I</button><button type="button" class="format-button underline" title="Underline" aria-label="Underline" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('underline')">U</button><input type="color" aria-label="Text color" title="Text color" value="#344956" @mousedown="rememberSignatureSelection" @input="applySignatureColor" /><button type="button" class="format-button" title="Align left" aria-label="Align left" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('justifyLeft')"><AlignLeft :size="15" /></button><button type="button" class="format-button" title="Align center" aria-label="Align center" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('justifyCenter')"><AlignCenter :size="15" /></button><button type="button" class="format-button" title="Align right" aria-label="Align right" @mousedown.prevent="rememberSignatureSelection" @click="formatSignature('justifyRight')"><AlignRight :size="15" /></button><button type="button" class="mail-icon-button insert-logo-button" @mousedown.prevent="rememberSignatureSelection" @click="insertSignatureLogo"><ImagePlus :size="14" /> {{ tx('插入 Logo','Insert logo') }}</button><button type="button" class="mail-icon-button signature-layout-button" @mousedown.prevent="rememberSignatureSelection" @click="arrangeSignatureSideBySide">{{ tx('左右布局','Side-by-side') }}</button></div><div class="signature-size-controls"><span class="signature-selection-label">{{ signatureSelectedTarget === 'logo' ? tx('Logo尺寸','Logo size') : tx('已选栏位','Selected column') }}</span><template v-if="signatureSelectedTarget === 'logo'"><label>{{ tx('宽度 px','Width px') }}<input v-model.number="signatureLogoWidthPx" type="number" min="1" max="1400" @change="applySignatureLogoDimensions('width')" /></label><label>{{ tx('高度 px','Height px') }}<input v-model.number="signatureLogoHeightPx" type="number" min="1" max="1400" :disabled="signatureLockAspect" @change="applySignatureLogoDimensions('height')" /></label><label class="signature-lock-ratio"><input v-model="signatureLockAspect" type="checkbox" @change="applySignatureLogoDimensions('width')" />{{ tx('锁定比例','Lock ratio') }}</label></template><label v-if="hasSignatureColumns">{{ tx('文字栏宽度 %','Text column %') }}<input v-model.number="signatureTextColumnWidth" type="number" min="10" max="90" @change="applySignatureColumnWidth" /></label><label v-if="hasSignatureColumns">{{ tx('水平对齐','Horizontal align') }}<select v-model="signatureHorizontalAlign" @change="applySignatureAlignment"><option value="left">{{ tx('左','Left') }}</option><option value="center">{{ tx('居中','Center') }}</option><option value="right">{{ tx('右','Right') }}</option></select></label><label v-if="hasSignatureColumns">{{ tx('垂直对齐','Vertical align') }}<select v-model="signatureVerticalAlign" @change="applySignatureAlignment"><option value="top">{{ tx('顶部','Top') }}</option><option value="middle">{{ tx('居中','Middle') }}</option><option value="bottom">{{ tx('底部','Bottom') }}</option></select></label></div><div ref="signatureEditor" class="signature-design-canvas" contenteditable="true" role="textbox" aria-multiline="true" :aria-label="tx('邮件签名编辑区','Email signature editor')" @click="selectSignatureTarget" @input="updateSignatureDraft" @mouseup="rememberSignatureSelection" @keyup="rememberSignatureSelection"></div></div><aside class="signature-preview-panel"><h4>{{ tx("预览","Preview") }}</h4><div class="signature-preview-canvas" v-html="sanitizeSignatureHtml(signatureHtmlDraft)"></div></aside></div><button type="submit" class="mail-primary signature-save" :disabled="busy">{{ busy ? tx('保存中…','Saving…') : tx('保存签名设计','Save signature design') }}</button></form>
    </section></div>
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
.compose-backdrop{position:fixed;inset:0;z-index:1400;display:grid;place-items:center;overflow-y:auto;padding:16px;background:#263945bb}
.compose-card{display:grid;gap:12px;box-sizing:border-box;width:min(740px,96vw);max-height:calc(100dvh - 32px);overflow:auto;padding:19px;border:1px solid #d2dde3;border-radius:14px;background:#fff;color:#304451;box-shadow:0 22px 70px #182d3a55}
.compose-backdrop-full{padding:12px}
.mail-compose-card{display:flex;flex-direction:column;width:calc(100vw - 24px);max-width:none;height:calc(100dvh - 24px);max-height:none;gap:5px;padding:9px 14px;overflow:auto}
.mail-compose-card>header,.mail-compose-card>label,.mail-compose-card .recipient-picker,.mail-compose-card .compose-address-grid,.mail-compose-card .compose-attachment-list,.mail-compose-card .consent-check,.mail-compose-card>footer{flex:0 0 auto}
.mail-compose-card>header{padding-bottom:8px}
.mail-compose-card .recipient-picker{gap:6px;padding:8px}
.mail-compose-card .recipient-options{max-height:92px}
.mail-compose-card .compose-header-inline{display:grid;grid-template-columns:150px minmax(0,1fr) 34px;align-items:center;gap:12px;min-height:42px;padding-bottom:5px}
.mail-compose-card .compose-title{min-width:0}
.mail-compose-card .compose-title .compose-eyebrow{margin:0;font-size:8px}
.mail-compose-card .compose-title h2{font-size:16px}
.mail-compose-card .compose-head-fields{display:grid;grid-template-columns:minmax(220px,1fr) minmax(180px,1fr);align-items:end;gap:9px;min-width:0}
.mail-compose-card .compose-head-fields.single{grid-template-columns:minmax(0,1fr)}
.mail-compose-card .compose-head-fields label,.mail-compose-card .compose-address-grid label{display:grid;gap:2px;min-width:0;color:#425966;font-size:10px;font-weight:650}
.mail-compose-card .compose-head-fields select,.mail-compose-card .compose-address-grid input{min-height:31px;padding:4px 8px;font-size:11px}
.mail-compose-card .customer-picker-trigger{display:inline-flex;min-height:32px;align-items:center;gap:7px;padding:4px 11px;border:1px solid #cfdae0;border-radius:999px;background:#f8fafb;color:#405969;font:inherit;font-size:11px;font-weight:650;cursor:pointer}
.mail-compose-card .customer-picker-trigger:hover{background:#eaf0f3}
.mail-compose-card .customer-picker-trigger span{display:grid;min-width:19px;height:19px;place-items:center;border-radius:50%;background:#405969;color:#fff;font-size:10px}
.customer-picker-backdrop{position:fixed;inset:0;z-index:1501;display:grid;place-items:center;padding:18px;background:#26394588}
.customer-picker-card{display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;gap:10px;box-sizing:border-box;width:min(650px,94vw);max-height:min(680px,88dvh);padding:16px;border:1px solid #d2dde3;border-radius:12px;background:#fff;color:#304451;box-shadow:0 18px 60px #182d3a55}
.customer-picker-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:8px;border-bottom:1px solid #e5ebee}
.customer-picker-card h3{margin:0 0 3px;font-size:16px}.customer-picker-card header p{margin:0;color:#71818a;font-size:11px}
.customer-picker-card header button{display:grid;width:32px;height:32px;place-items:center;border:1px solid #d6e0e5;border-radius:50%;background:#fff;color:#405969;cursor:pointer}
.customer-picker-card>input{box-sizing:border-box;width:100%;min-height:36px;padding:7px 10px;border:1px solid #d3dfe5;border-radius:6px;font:inherit;font-size:12px}
.customer-picker-options{display:grid;align-content:start;gap:2px;min-height:0;overflow:auto}
.customer-picker-options .recipient-option{min-height:48px}
.customer-picker-card>footer{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-top:9px;border-top:1px solid #e5ebee}
.customer-picker-card>footer span{color:#71818a;font-size:11px}
.mail-compose-card .compose-address-grid{display:grid;grid-template-columns:auto minmax(240px,2fr) minmax(130px,1fr) minmax(220px,2fr);align-items:end;gap:8px}
.mail-compose-card .compose-address-grid .customer-picker-trigger{min-height:31px;margin-bottom:1px}
.mail-compose-card>label{gap:3px}
.mail-compose-card input,.mail-compose-card select{min-height:34px;padding:6px 9px}
.mail-compose-card .compose-editor-shell{display:flex;min-height:0;min-width:0;flex:1 1 auto;flex-direction:column;overflow:hidden;border:1px solid #d3dfe5;border-radius:8px;background:#fff}
.mail-compose-card .compose-toolbar{display:flex;flex:0 0 auto;align-items:center;gap:4px;flex-wrap:wrap;padding:5px;border-bottom:1px solid #dfe7eb;background:#f3f6f7}
.mail-compose-card .compose-toolbar select{width:auto;min-width:78px;max-width:155px;height:32px;min-height:32px;padding:3px 6px;font-size:11px}
.mail-compose-card .compose-toolbar button{display:inline-flex;min-width:30px;min-height:30px;align-items:center;justify-content:center;gap:4px;padding:3px 8px;border:1px solid #cfdae0;border-radius:5px;background:#fff;color:#405969;font:inherit;font-size:11px;cursor:pointer}
.mail-compose-card .compose-toolbar button:hover{background:#e7eef2}
.mail-compose-card .compose-toolbar button.active{border-color:#8399a7;background:#e6edf1;color:#304451}
.mail-compose-card .compose-toolbar .compose-attachment-limit{padding:0 4px;color:#73838c;font-size:10px}
.mail-compose-card .compose-toolbar input[type=color]{width:32px;height:32px;min-width:32px;min-height:32px;padding:3px}
.mail-compose-card .compose-image-controls{display:flex;flex:0 0 auto;align-items:flex-end;gap:9px;flex-wrap:wrap;padding:5px 9px;border-bottom:1px solid #e4eaed;background:#fbfcfc}
.mail-compose-card .compose-image-controls label{display:grid;gap:3px;color:#536875;font-size:10px;font-weight:650}
.mail-compose-card .compose-image-controls input,.mail-compose-card .compose-image-controls select{width:110px;min-height:29px;padding:3px 6px;font-size:11px}
.mail-compose-card .compose-image-controls button{display:inline-flex;min-height:29px;align-items:center;gap:5px;padding:3px 9px;border:1px solid #cfdae0;border-radius:999px;background:#fff;color:#405969;font:inherit;font-size:10px;cursor:pointer}
.mail-compose-card .compose-image-controls span{padding-bottom:7px;color:#73838c;font-size:10px}
.mail-compose-card .compose-editor-canvas{box-sizing:border-box;min-height:0;max-height:none;flex:1 1 auto;overflow:auto;padding:20px 22px;outline:none;background:#fff;color:#304451;font:14px/1.65 Arial,sans-serif;overflow-wrap:anywhere}
.mail-compose-card .compose-editor-canvas:focus{box-shadow:inset 0 0 0 2px #9eafba}
.mail-compose-card .compose-editor-canvas p{margin:0 0 10px}
.mail-compose-card .compose-editor-canvas h2{margin:16px 0 9px;font-size:23px}
.mail-compose-card .compose-editor-canvas h3{margin:13px 0 8px;font-size:18px}
.mail-compose-card .compose-editor-canvas blockquote{margin:10px 0;padding:5px 12px;border-left:3px solid #9eafba;color:#60727d}
.mail-compose-card .compose-editor-canvas img{height:auto;max-width:100%}
.mail-compose-card .compose-editor-hint{flex:0 0 auto;padding:6px 10px;border-top:1px solid #edf1f3;color:#73838c;font-size:10px}
.mail-compose-card .compose-attachment-list{display:flex;align-items:center;gap:7px;flex-wrap:wrap;padding:4px 0}
.mail-compose-card .compose-attachment-list>span{display:inline-flex;align-items:center;gap:5px;padding:4px 7px;border:1px solid #dce5e9;border-radius:999px;background:#f8fafb;color:#50636f;font-size:10px}
.mail-compose-card .compose-attachment-list button{display:grid;width:20px;height:20px;place-items:center;border:0;border-radius:50%;background:transparent;color:#60727d;cursor:pointer}
.mail-compose-card .compose-attachment-list small{color:#74838c;font-size:10px}
.mail-compose-card footer{margin:0 -18px -14px;padding:9px 18px}
.compose-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-bottom:12px;border-bottom:1px solid #e5ebee}
.compose-card>header h2{margin:0;color:#304451;font-size:20px}.compose-card>header button{display:grid;place-items:center;width:36px;height:36px;border:1px solid #d6e0e5;border-radius:50%;background:#fff;color:#405969;cursor:pointer}
.compose-card>label{display:grid;gap:5px;color:#425966;font-size:12px;font-weight:650}.compose-card textarea{resize:vertical;line-height:1.5}
.compose-card footer{position:sticky;bottom:-19px;display:flex;align-items:center;justify-content:space-between;gap:12px;margin:4px -19px -19px;padding:12px 19px;border-top:1px solid #e5ebee;background:#fff}.compose-card footer span{color:#687b86;font-size:11px}
.mail-compose-card>header{padding-bottom:8px}
.mail-compose-card>label{gap:3px}
.mail-compose-card footer{margin:0 -18px -14px;padding:9px 18px}
.mail-settings-card{width:min(1280px,98vw);gap:13px}.template-editor,.signature-editor,.signature-logo-editor{gap:10px;padding:13px;border:1px solid #d8e2e7;border-radius:9px;background:#f8fafb}.mail-settings-card h3{margin:0;font-size:15px;color:#344956}.signature-logo-editor{display:grid}.signature-logo-editor>p{margin:0;color:#647782;font-size:12px;line-height:1.5}.signature-logo-actions{display:flex;gap:8px;flex-wrap:wrap}.signature-logo-editor>.mail-help{margin:0}
.signature-editor-help{margin:0;color:#647782;font-size:12px;line-height:1.5}
.signature-design-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px;align-items:stretch}
.signature-editor-workspace,.signature-preview-panel{min-width:0;border:1px solid #d7e1e6;border-radius:8px;background:#fff;overflow:hidden}
.signature-toolbar{display:flex;align-items:center;gap:5px;flex-wrap:wrap;padding:7px;border-bottom:1px solid #dfe7eb;background:#f3f6f7}
.signature-toolbar select{width:auto;min-width:72px;height:32px;min-height:32px!important;padding:3px 6px;border:1px solid #cfdae0;border-radius:5px;background:#fff;color:#40515c;font:inherit;font-size:11px}
.signature-toolbar select:first-child{min-width:112px}
.signature-size-controls{display:flex;align-items:flex-end;gap:8px;flex-wrap:wrap;padding:8px;border-bottom:1px solid #e4eaed;background:#fbfcfc}
.signature-size-controls>label{display:grid;gap:3px;color:#536875;font-size:10px;font-weight:650}
.signature-size-controls input[type=number],.signature-size-controls select{width:90px;min-width:90px;height:30px;min-height:30px!important;padding:3px 6px;border:1px solid #cfdae0;border-radius:5px;background:#fff;color:#40515c;font:inherit;font-size:11px}
.signature-size-controls input[type=number]:disabled{background:#eef1f3;color:#89949a}
.signature-size-controls .signature-lock-ratio{display:flex;align-items:center;gap:5px;min-height:30px}
.signature-size-controls .signature-lock-ratio input{width:14px;height:14px;margin:0;accent-color:#405969}
.signature-selection-label{padding:0 4px 7px 0;color:#344956;font-size:10px;font-weight:750;white-space:nowrap}
.mail-workspace .signature-toolbar button.format-button{display:grid;place-items:center;width:30px;height:30px;min-width:30px;min-height:30px!important;padding:0;border:1px solid #d0dbe1;border-radius:5px;background:#fff;color:#405969;font-size:13px}
.mail-workspace .signature-toolbar button.format-button:hover{background:#e7eef2}
.signature-toolbar input[type=color]{width:32px;height:32px;min-width:32px;min-height:32px!important;padding:3px;border:1px solid #cfdae0;border-radius:5px;background:#fff}
.mail-workspace .signature-toolbar button.insert-logo-button,.mail-workspace .signature-toolbar button.signature-layout-button{min-height:32px!important;padding:3px 8px;font-size:11px}
.signature-design-canvas{min-height:190px;max-height:320px;overflow:auto;padding:14px 16px;outline:none;background:#fff;color:#344956;font:13px/1.55 Arial,sans-serif;overflow-wrap:anywhere}
.signature-design-canvas:focus{box-shadow:inset 0 0 0 2px #9eafba}
.signature-design-canvas:empty:before{content:"Type your name and contact details…";color:#9aa8af;pointer-events:none}
.signature-design-canvas p{margin:0 0 7px}.signature-design-canvas p:last-child{margin-bottom:0}
.signature-preview-panel{padding:12px;background:#f3f6f7}
.signature-preview-panel h4{margin:0 0 9px;color:#60727d;font-size:10px;font-weight:700;letter-spacing:.1em;text-transform:uppercase}
.signature-preview-canvas{min-height:120px;padding:13px;border:1px solid #e0e7eb;border-radius:5px;background:#fff;color:#344956;font:13px/1.55 Arial,sans-serif;overflow-wrap:anywhere}
.signature-preview-canvas :deep(p){margin:0 0 7px}.signature-preview-canvas :deep(p:last-child){margin-bottom:0}
.signature-preview-canvas :deep(img){max-width:100%;height:auto;vertical-align:middle}
.signature-preview-canvas :deep(table){max-width:100%;border-collapse:collapse}
.signature-preview-canvas :deep(td){vertical-align:middle}
.signature-design-canvas table,.signature-preview-canvas :deep(table){width:100%;table-layout:fixed;border-collapse:collapse}
.signature-design-canvas td,.signature-preview-canvas :deep(td){box-sizing:border-box;overflow-wrap:anywhere}
.signature-design-canvas td{min-width:0}
.signature-preview-canvas :deep(img),.signature-design-canvas img{height:auto;max-width:100%}
.signature-save{justify-self:start}
.template-editor>label,.signature-editor>label{font-size:12px;color:#425966}.template-editor textarea,.signature-editor textarea{min-height:92px}
.signature-preview{max-width:260px;max-height:100px}
@media(max-width:1050px){.mail-client{grid-template-columns:165px minmax(270px,330px) minmax(0,1fr)}.mail-reader-content{padding:18px}.mail-reader-head{display:grid}.mail-reader-actions{justify-content:flex-start}}
@media(max-width:760px){.mail-workspace{min-height:calc(100dvh - 110px)}.mail-page-head{align-items:flex-start;flex-direction:column}.mail-head-actions{width:100%;flex-wrap:wrap}.mail-client{height:auto;min-height:78dvh;grid-template-columns:118px minmax(0,1fr);grid-template-rows:minmax(270px,42dvh) minmax(340px,1fr)}.mail-sidebar{grid-column:1;grid-row:1/3;padding:9px 5px}.mail-folder{min-height:38px;padding:0 8px;font-size:11px}.mail-message-list{grid-column:2;grid-row:1;border-right:0;border-bottom:1px solid #e1e8ec}.mail-reader{grid-column:2;grid-row:2}.mail-reader-content{padding:14px}.mail-list-toolbar{padding:10px}.mail-list-toolbar input{width:100%}.mail-row{min-height:66px;padding:10px}.mail-connect-card{margin-top:10px;padding:18px}}
@media(max-width:900px){.mail-client{grid-template-columns:130px minmax(220px,35%) minmax(300px,1fr)}.mail-reader-head{display:grid}.mail-reader-actions{justify-content:flex-start}}
@media(max-width:760px){.mail-client{grid-template-columns:118px minmax(0,1fr)}}
@media(max-width:800px){.signature-design-grid{grid-template-columns:1fr}.signature-preview-canvas{min-height:90px}.signature-design-canvas{min-height:160px}}
@media(max-width:760px){.compose-backdrop-full{padding:6px}.mail-compose-card{width:calc(100vw - 12px);height:calc(100dvh - 12px);padding:8px}.mail-compose-card .compose-header-inline{grid-template-columns:1fr 34px;gap:6px}.mail-compose-card .compose-title{grid-column:1}.mail-compose-card .compose-head-fields{grid-column:1/-1;grid-row:2;grid-template-columns:minmax(0,1fr) minmax(0,1fr)}.mail-compose-card .compose-address-grid{grid-template-columns:auto minmax(0,1fr);gap:5px}.mail-compose-card .compose-address-grid label:nth-of-type(2){grid-column:2}.mail-compose-card .compose-address-grid label:nth-of-type(3){grid-column:1/-1}.mail-compose-card .compose-toolbar select{max-width:115px}.mail-compose-card .compose-editor-shell{min-height:220px}.mail-compose-card .compose-editor-canvas{padding:14px}.mail-compose-card footer{margin:0 -8px -8px;padding:8px}.customer-picker-card{max-height:90dvh;padding:12px}}
@media(max-width:480px){.mail-compose-card .compose-head-fields{grid-template-columns:minmax(0,1fr)}.mail-compose-card .compose-address-grid{grid-template-columns:minmax(0,1fr)}.mail-compose-card .compose-address-grid .customer-picker-trigger,.mail-compose-card .compose-address-grid label{grid-column:1!important}.mail-compose-card .compose-toolbar{gap:3px}.mail-compose-card .compose-toolbar select{max-width:96px;min-width:65px}}
</style>
