<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { portalSession, portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const invoices = ref<any[]>([]);
const rebates = ref<any[]>([]);
const reportedUnpaidCount = ref<number | null>(null);
const loading = ref(true);
const downloading = ref("");
const error = ref("");
const unpaidCount = computed(() => reportedUnpaidCount.value ?? invoices.value.filter((invoice) => invoice.payment_status !== "received" && invoice.payment_status !== "paid").length);

function paid(invoice: any): boolean { return invoice.payment_status === "received" || invoice.payment_status === "paid"; }
function statusText(invoice: any): string {
  if (paid(invoice)) return tx("已付款", "Paid");
  if (invoice.status === "draft") return tx("待发送", "Draft");
  return tx("未付款", "Unpaid");
}
function invoiceOrderNames(invoice: any): string {
  return (invoice.orders || []).map((order: any) => order.order_number || order.project_name).filter(Boolean).join(", ");
}

onMounted(async () => {
  try {
    const result = await portalRequest<any>("invoices");
    invoices.value = Array.isArray(result) ? result : (result.invoices || []);
    if (!Array.isArray(result) && typeof result.unpaid_count === "number") reportedUnpaidCount.value = result.unpaid_count;
    rebates.value = Array.isArray(result) ? [] : (result.rebates || []);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : tx("发票暂时无法载入。", "Invoices could not be loaded.");
  } finally {
    loading.value = false;
  }
});

async function download(invoice: any) {
  if (!invoice?.id || downloading.value) return;
  error.value = "";
  downloading.value = invoice.id;
  try {
    const response = await fetch(`/api/portal/invoices/${encodeURIComponent(invoice.id)}/pdf`, {
      headers: portalSession.token ? { Authorization: `Bearer ${portalSession.token}` } : {},
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      if (response.status === 401) portalSession.token = "";
      throw new Error(typeof body.detail === "string" ? body.detail : response.statusText || "PDF unavailable");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    const disposition = response.headers.get("Content-Disposition") || "";
    const filename = disposition.match(/filename\*?=(?:UTF-8''|\")?([^;\"]+)/i)?.[1];
    anchor.href = objectUrl;
    anchor.download = filename ? decodeURIComponent(filename.replace(/^"|"$/g, "")) : `${invoice.invoice_number || invoice.id}.pdf`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : tx("PDF 下载失败，请稍后重试。", "Could not download the PDF. Please try again.");
  } finally {
    downloading.value = "";
  }
}
</script>

<template>
  <div class="invoices-page">
    <header class="page-heading"><div><p class="eyebrow">{{ tx("账户", "ACCOUNT") }}</p><h1>{{ tx("发票与付款", "Invoices & payments") }}</h1><p class="subtitle">{{ tx("查看账单、付款状态并下载 PDF。", "Review invoices, payment status and PDF copies.") }}</p></div><div class="unpaid-count" :class="{ clear: unpaidCount===0 }"><strong>{{ unpaidCount }}</strong><span>{{ tx("张未付款", "unpaid") }}</span></div></header>

    <div v-if="loading" class="notice">{{ tx("加载中…", "Loading…") }}</div>
    <div v-else-if="error && !invoices.length" class="error-box" role="alert">{{ error }}</div>
    <div v-else>
      <div v-if="error" class="error-box" role="alert">{{ error }}</div>
      <div v-if="invoices.length" class="invoice-list">
        <article v-for="invoice in invoices" :key="invoice.id" class="invoice-card" :class="paid(invoice)?'is-paid':'is-unpaid'">
          <div class="invoice-head"><div><p class="invoice-kind">{{ invoice.kind === "deposit" ? tx("定金发票", "Deposit invoice") : invoice.kind === "balance" ? tx("尾款发票", "Balance invoice") : tx("服务账单", "Service invoice") }}</p><h2>{{ invoice.invoice_number || tx("发票", "Invoice") }}</h2></div><span class="payment-pill" :class="paid(invoice)?'paid':'unpaid'">{{ statusText(invoice) }}</span></div>
          <div class="invoice-meta"><span>{{ tx("开票日期", "Issued") }}: {{ (invoice.created_at || "").slice(0,10) || "—" }}</span><span v-if="invoice.reference">{{ tx("参考号（订单号）", "Reference") }}: <strong>{{ invoice.reference }}</strong></span><span v-if="invoice.orders?.length">{{ tx("订单", "Orders") }}: {{ invoiceOrderNames(invoice) }}</span></div>
          <div v-if="invoice.balance_lines?.length || invoice.deposit_lines?.length" class="balance-breakdown">
            <div class="breakdown-heading">{{ invoice.kind === 'deposit' ? tx("定金账单汇总", "Deposit summary") : tx("订单尾款明细", "Order balance details") }}</div>
            <div v-for="(line, index) in invoice.deposit_lines || []" :key="`${invoice.id}-deposit-${index}`" class="breakdown-row"><span><strong>{{ line.order_number || line.project_name }}</strong><small>{{ tx("订单总额", "Order total") }} · {{ invoice.currency || "NZD" }} {{ line.order_total }}</small></span><span>{{ tx("定金", "Deposit") }} · {{ invoice.currency || "NZD" }} {{ line.deposit_due }}</span></div>
            <div v-for="(line, index) in invoice.balance_lines" :key="`${invoice.id}-${index}`" class="breakdown-row"><span><strong>{{ line.order_number || line.project_name }}</strong><small v-if="line.order_number && line.project_name">{{ line.project_name }}</small></span><span>{{ invoice.currency || "NZD" }} {{ line.amount }}</span></div>
            <div v-for="(line, index) in invoice.additional_lines || []" :key="`${invoice.id}-extra-${index}`" class="breakdown-row"><span>{{ line.description }}</span><span>{{ invoice.currency || "NZD" }} {{ line.amount }}</span></div>
            <div v-if="invoice.rebate_allocations?.length" class="breakdown-credit">
              <div v-for="(rebate, index) in invoice.rebate_allocations" :key="`${invoice.id}-rebate-${index}`" class="breakdown-row"><span>{{ tx("返利抵扣", "Rebate credit") }} · {{ rebate.month || "—" }}</span><span>−{{ invoice.currency || "NZD" }} {{ rebate.amount }}</span></div>
            </div>
            <div v-if="invoice.gross_amount && invoice.rebate_allocations?.length" class="breakdown-row breakdown-subtotal"><span>{{ tx("抵扣前尾款合计", "Balance before rebate") }}</span><span>{{ invoice.currency || "NZD" }} {{ invoice.gross_amount }}</span></div>
          </div>
          <div class="invoice-foot"><div class="invoice-total"><small>{{ tx("其中 GST", "Includes GST") }} ({{ Math.round(Number(invoice.gst_rate || 0.15)*100) }}%): {{ invoice.currency || "NZD" }} {{ invoice.gst_amount }}</small><strong class="amount">{{ tx("应付总额（含 GST）", "Amount due (incl. GST)") }} · {{ invoice.currency || "NZD" }} {{ invoice.amount }}</strong></div><button type="button" class="download-button" :disabled="downloading===invoice.id" @click="download(invoice)">{{ downloading===invoice.id ? tx("准备中…", "Preparing…") : tx("下载 PDF", "Download PDF") }}</button></div>
        </article>
      </div>
      <div v-else class="empty-state"><span class="empty-icon">▤</span><h2>{{ tx("还没有发票", "No invoices yet") }}</h2><p>{{ tx("发票开具后会显示在这里。", "Invoices will appear here when they are issued.") }}</p></div>

      <section v-if="rebates.length" class="rebates-section"><h2>{{ tx("返利余额", "Rebate balance") }}</h2><div class="rebate-list"><article v-for="rebate in rebates" :key="rebate.id" class="rebate-card"><strong>{{ rebate.month || rebate.id }}</strong><span>{{ rebate.currency }} {{ rebate.remaining || rebate.amount }}</span></article></div></section>
    </div>
  </div>
</template>

<style scoped>
.invoices-page{max-width:1100px;margin:auto;color:var(--ink,#1b2421)}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin:4px 0 22px}.eyebrow{margin:0 0 5px;color:var(--cord);font-size:11px;font-weight:750;letter-spacing:.12em}.page-heading h1{margin:0;font:600 28px var(--font-display)}.subtitle{margin:6px 0 0;color:#65736c;font-size:13px}.unpaid-count{display:flex;align-items:baseline;gap:8px;padding:10px 14px;border:1px solid #ebc8c2;border-radius:8px;background:#fff4f1;color:#a44034;white-space:nowrap}.unpaid-count strong{font-size:25px}.unpaid-count span{font-size:12px;font-weight:650}.unpaid-count.clear{border-color:#cfe0d3;background:#eff6f0;color:#286444}.invoice-list{display:grid;gap:12px}.invoice-card{padding:16px 18px;border:1px solid #e5c7c2;border-left:4px solid #bd584d;border-radius:7px;background:#fff}.invoice-card.is-paid{border-color:#d1e1d5;border-left-color:#33835a}.invoice-head,.invoice-foot{display:flex;align-items:center;justify-content:space-between;gap:14px}.invoice-kind{margin:0 0 3px;color:#6a786f;font-size:11px;text-transform:uppercase;letter-spacing:.07em}.invoice-head h2{margin:0;font-size:17px}.payment-pill{padding:5px 10px;border-radius:999px;font-size:12px;font-weight:700}.payment-pill.paid{background:#e7f3ea;color:#21613e}.payment-pill.unpaid{background:#fff0ed;color:#a44034}.invoice-meta{display:flex;flex-wrap:wrap;gap:8px 18px;margin:12px 0;color:#6b7971;font-size:12px}.balance-breakdown{margin:10px 0 12px;padding:10px 12px;border:1px solid #e5ebea;border-radius:8px;background:#fbfcfc}.breakdown-heading{margin-bottom:4px;color:#596b71;font-size:11px;font-weight:750;letter-spacing:.06em;text-transform:uppercase}.breakdown-row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px solid #edf0ef;font-size:12px;font-variant-numeric:tabular-nums}.breakdown-row:last-child{border-bottom:0}.breakdown-row>span:first-child{display:grid;gap:2px}.breakdown-row small{color:#718087}.breakdown-credit{color:#536d56}.breakdown-subtotal{border:0;color:#637178}.invoice-foot{padding-top:12px;border-top:1px solid #edf0ed}.amount{font-size:17px}.download-button{min-height:38px;padding:8px 12px;border:1px solid #9eb5a5;border-radius:999px;background:#fff;color:#22573d;font-size:13px;font-weight:650;cursor:pointer}.download-button:hover{background:#edf5ef;border-color:#4e8b65}.download-button:disabled{opacity:.55;cursor:wait}.empty-state,.notice{text-align:center;padding:42px 18px;border:1px solid #dbe4dd;border-radius:8px;background:#fff;color:#68766e}.empty-state h2{margin:9px 0 4px;color:#31463a;font-size:18px}.empty-state p{margin:0;font-size:13px}.empty-icon{font-size:27px;color:#718278}.error-box{margin:12px 0;padding:12px 14px;background:#fff0ed;color:#8f3425;border-radius:6px;font-size:13px}.rebates-section{margin-top:28px}.rebates-section h2{font:600 19px var(--font-display)}.rebate-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px}.rebate-card{display:flex;justify-content:space-between;gap:10px;padding:14px;background:#f3f7f3;border:1px solid #dbe4dd;border-radius:6px}.rebate-card span{font-weight:650}@media(max-width:600px){.page-heading{align-items:flex-start}.page-heading h1{font-size:23px}.unpaid-count{padding:7px 10px;gap:5px}.unpaid-count strong{font-size:21px}.unpaid-count span{font-size:10px}.invoice-card{padding:13px}.invoice-head h2{font-size:15px}.invoice-meta{display:grid;gap:5px}.invoice-foot{align-items:flex-end}}
</style>
<style scoped>
.invoice-total{display:grid;gap:4px}.invoice-total small{color:#64736c;font-size:11px}
</style>
