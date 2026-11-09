<script setup lang="ts">
import { onMounted, ref } from "vue";
import { portalRequest } from "../../portal-api";

interface RebateOrder { order_id: string; order_number?: string; order_id_label?: string; order_date: string; product_total: string; currency: string; rate: number; rebate: string }
interface RebateMonth { month: string; product_total: string; rebate: string; currency: string; orders: RebateOrder[] }
const months = ref<RebateMonth[]>([]);
const expanded = ref<string | null>(null);
const loading = ref(true);
const error = ref("");
const money = (amount: string, currency: string) => new Intl.NumberFormat("en-NZ", { style: "currency", currency }).format(Number(amount || 0));
const monthName = (month: string) => new Intl.DateTimeFormat("en-NZ", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(`${month}-01T00:00:00Z`));
onMounted(async () => {
  try { const result = await portalRequest<{ months: RebateMonth[] }>("rebates"); months.value = result.months; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
});
</script>

<template>
  <section class="rebates">
    <header><p class="eyebrow">CUSTOMER REBATE</p><h1>My Rebate</h1><p class="rule">Each calendar month is calculated from orders by deposit paid date. When product totals exceed NZD $10,000, that month earns a 5% rebate. Months are calculated separately; unused totals do not carry forward.</p></header>
    <p v-if="loading" class="message">Loading rebate history…</p>
    <p v-else-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-else-if="!months.length" class="message">No deposit-paid orders are available for rebate history yet.</p>
    <div v-else class="month-list">
      <article v-for="item in months" :key="item.month" class="month-card">
        <div class="month-main"><div><h2>{{ monthName(item.month) }}</h2><p>{{ item.orders.length }} qualifying deposit-paid order{{ item.orders.length === 1 ? "" : "s" }}</p></div><dl><div><dt>Product total</dt><dd>{{ money(item.product_total, item.currency) }}</dd></div><div><dt>Rebate earned</dt><dd class="rebate-amount">{{ money(item.rebate, item.currency) }}</dd></div></dl><button type="button" :aria-expanded="expanded === item.month" @click="expanded = expanded === item.month ? null : item.month">{{ expanded === item.month ? "Hide details" : "View details" }}</button></div>
        <div v-if="expanded === item.month" class="details"><div class="detail-row detail-head"><span>Order ID</span><span>Deposit paid</span><span>Product total</span><span>Rebate rate</span><span>Rebate</span></div><div v-for="order in item.orders" :key="order.order_id" class="detail-row"><span>{{ order.order_number || order.order_id_label || order.order_id }}</span><span>{{ order.order_date }}</span><span>{{ money(order.product_total, order.currency) }}</span><span>{{ (order.rate * 100).toFixed(0) }}%</span><span>{{ money(order.rebate, order.currency) }}</span></div></div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.rebates{max-width:1100px;margin:auto;color:#28343a}.eyebrow{margin:0 0 5px;font-size:11px;letter-spacing:.14em;font-weight:700;color:#687a83}.rebates h1{margin:0 0 10px;font-size:28px}.rule{max-width:80ch;margin:0 0 22px;color:#56666e;line-height:1.6}.message{padding:18px;background:#f2f5f5;border-radius:7px;color:#56666e}.error{color:#8b322b}.month-list{display:grid;gap:10px}.month-card{border:1px solid #d6dfe1;border-radius:7px;background:#fff}.month-main{display:grid;grid-template-columns:minmax(160px,1fr) minmax(280px,1.2fr) auto;align-items:center;gap:20px;padding:16px}.month-main h2{margin:0;font-size:17px}.month-main p{margin:4px 0 0;color:#6b7a80;font-size:12px}.month-main dl{display:flex;gap:28px;margin:0}.month-main dl div{display:grid;gap:4px}.month-main dt{font-size:11px;color:#6b7a80}.month-main dd{margin:0;font-weight:650}.rebate-amount{color:#354f5b}.month-main button{min-height:36px;padding:7px 12px;border:1px solid #9dacb1;border-radius:5px;background:#fff;color:#344b56;font-weight:600;cursor:pointer}.month-main button:hover{background:#edf2f3}.details{border-top:1px solid #e1e7e8;padding:6px 16px 12px;overflow:auto}.detail-row{display:grid;grid-template-columns:minmax(150px,1.4fr) minmax(120px,1fr) repeat(3,minmax(105px,.8fr));gap:14px;padding:9px 0;border-bottom:1px solid #eef1f1;font-size:12px}.detail-row:last-child{border-bottom:0}.detail-head{font-size:10px;font-weight:700;letter-spacing:.06em;color:#63737a;text-transform:uppercase}@media(max-width:700px){.month-main{grid-template-columns:1fr;gap:12px}.month-main dl{justify-content:space-between}.detail-row{min-width:650px}}
</style>
