<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { request } from '../crm-api';

interface Order {
  id: string; order_number?: string; company: string; project_name: string; status: string;
  payment_status: string; total?: string | null; deposit?: string | null; eta?: string;
  subtotal?: string | null; installation?: string | null; tax?: string | null;
  created_at?: string; accepted_at?: string; deposit_paid_at?: string; order_date?: string | null;
  history?: { action: string; created_at: string }[];
}
interface Invoice { kind: string; payment_status?: string; received_at?: string; amount: string; order_ids?: string[]; }
const router = useRouter();
const { locale } = useI18n();
const zh = computed(() => locale.value === 'zh');
const tx = (cn: string, en: string) => zh.value ? cn : en;
const orders = ref<Order[]>([]);
const invoices = ref<Invoice[]>([]);
const loading = ref(true);
const error = ref('');
const selectedForOrdering = ref<string[]>([]);
const orderingBusy = ref(false);
const orderNotice = ref('');
const formatter = new Intl.NumberFormat('en-NZ', { style: 'currency', currency: 'NZD', minimumFractionDigits: 2, maximumFractionDigits: 2 });
const amount = (value?: string | number | null) => formatter.format(Number(value || 0));
const reviewTasks = computed(() => orders.value.filter(order => order.status === 'pending_review'));
const orderTasks = computed(() => orders.value.filter(order => order.status === 'accepted' && order.payment_status === 'deposit_received'));
const monthKey = (value?: string) => value ? value.slice(0, 7) : '';
const monthLabel = (key: string) => new Intl.DateTimeFormat(zh.value ? 'zh-NZ' : 'en-NZ', { month: 'short', year: 'numeric', timeZone: 'Pacific/Auckland' }).format(new Date(`${key}-01T12:00:00`));
const months = computed(() => {
  const result: string[] = [];
  const now = new Date();
  for (let i = 5; i >= -6; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1, 12);
    result.push(`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2, '0')}`);
  }
  return result;
});
const monthly = computed(() => months.value.map(month => {
  const bookedOrders = orders.value.filter(order => Boolean(order.order_date) && monthKey(order.order_date || undefined) === month);
  const booked = bookedOrders.reduce((sum, order) => sum + Number(order.total || 0), 0);
  const product = bookedOrders.reduce((sum, order) => sum + Number(order.subtotal || 0), 0);
  const installation = bookedOrders.reduce((sum, order) => sum + Number(order.installation || 0), 0);
  const gst = bookedOrders.reduce((sum, order) => sum + Number(order.tax || 0), 0);
  const received = invoices.value.filter(invoice => invoice.kind === 'deposit' && invoice.payment_status === 'received' && monthKey(invoice.received_at) === month).reduce((sum, invoice) => sum + Number(invoice.amount || 0), 0);
  const balance = orders.value.filter(order => order.payment_status === 'deposit_received' && order.eta && monthKey(order.eta) === month && ['accepted','supplier_ordered','in_transit','ready'].includes(order.status)).reduce((sum, order) => sum + Math.max(0, Number(order.total || 0) - Number(order.deposit || 0)), 0);
  return { month, booked, product, installation, gst, received, balance };
}));
const maxFinance = computed(() => Math.max(1, ...monthly.value.flatMap(row => [row.booked, row.product, row.installation, row.gst, row.received, row.balance])));
async function load() {
  loading.value = true;
  error.value = '';
  try {
    const [orderRows, invoiceRows] = await Promise.all([request<Order[]>('operations/orders'), request<Invoice[]>('operations/invoices')]);
    orders.value = orderRows;
    invoices.value = invoiceRows;
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { loading.value = false; }
}
function openOrders(status: string, payment?: string) {
  const query: Record<string, string> = {};
  if (status) query.status = status;
  if (payment) query.payment = payment;
  void router.push({ path: '/crm/projects', query });
}

function openOrder(order: Order) {
  void router.push({ path: '/crm/projects', query: { order: order.id, source: 'dashboard' } });
}

function toggleOrdering(orderId: string) {
  selectedForOrdering.value = selectedForOrdering.value.includes(orderId)
    ? selectedForOrdering.value.filter(id => id !== orderId)
    : [...selectedForOrdering.value, orderId];
}

async function markSelectedOrdered() {
  if (!selectedForOrdering.value.length || orderingBusy.value) return;
  orderingBusy.value = true;
  orderNotice.value = '';
  try {
    for (const id of selectedForOrdering.value) await request(`operations/orders/${id}/supplier-order`, {});
    selectedForOrdering.value = [];
    orderNotice.value = tx('已将所选订单标记为已下单。', 'Selected orders were marked as ordered.');
    await load();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally { orderingBusy.value = false; }
}
onMounted(() => void load());
</script>

<template>
  <main class="dashboard-live">
    <header class="dashboard-title"><div><p>{{ tx('业务概览','BUSINESS OVERVIEW') }}</p><h1>{{ tx('Dashboard','Dashboard') }}</h1></div><button type="button" @click="load">{{ tx('刷新','Refresh') }}</button></header>
    <p v-if="error" class="dashboard-error" role="alert">{{ error }}</p>
    <section class="task-area"><h2>{{ tx('需要处理的工作','Action required') }}</h2>
      <p v-if="orderNotice" class="dashboard-notice" role="status">{{ orderNotice }}</p>
      <div class="task-cards">
        <section class="task-card"><header><div><span>{{ tx('待审阅','Pending review') }}</span><strong>{{ reviewTasks.length }}</strong></div><small>{{ tx('客户已提交，等待审核','Submitted by customers and awaiting review') }}</small></header>
          <div v-if="reviewTasks.length" class="task-list"><button v-for="order in reviewTasks" :key="order.id" type="button" class="task-order" @click="openOrder(order)"><strong>{{ order.order_number || order.project_name || order.id }}</strong><span>{{ order.company }} · {{ order.project_name }}</span><b>{{ tx('审阅 →','Review →') }}</b></button></div>
          <p v-else class="task-empty">{{ tx('没有待审阅订单','No orders awaiting review') }}</p>
        </section>
        <section class="task-card"><header><div><span>{{ tx('待下单','Ready to order') }}</span><strong>{{ orderTasks.length }}</strong></div><small>{{ tx('已确认且定金已收，等待向工厂下单','Confirmed and deposit received; awaiting supplier order') }}</small></header>
          <div v-if="orderTasks.length" class="task-list"><label v-for="order in orderTasks" :key="order.id" class="task-order task-order-select"><input type="checkbox" :checked="selectedForOrdering.includes(order.id)" @change="toggleOrdering(order.id)" /><button type="button" @click="openOrder(order)"><strong>{{ order.order_number || order.project_name || order.id }}</strong><span>{{ order.company }} · {{ order.project_name }}</span></button></label></div>
          <p v-else class="task-empty">{{ tx('没有待下单订单','No orders awaiting supplier order') }}</p>
          <button v-if="orderTasks.length" type="button" class="task-bulk" :disabled="!selectedForOrdering.length || orderingBusy" @click="markSelectedOrdered">{{ orderingBusy ? tx('处理中…','Updating…') : tx(`标记已下单（${selectedForOrdering.length}）`,`Mark ordered (${selectedForOrdering.length})`) }}</button>
        </section>
      </div>
    </section>
    <section class="finance-area"><div class="section-title"><div><h2>{{ tx('财务概览','Financial overview') }}</h2><p>{{ tx('营业额按定金到账后的正式订单日期归月；已收款按实际到账日；尾款按 ETA 预测。','Revenue is grouped by the formal order date after deposit receipt; payments use the actual receipt date, and balances are forecast by ETA.') }}</p></div></div>
      <p v-if="loading" class="muted">{{ tx('正在读取真实订单…','Loading live order data…') }}</p>
      <div v-else class="finance-table-wrap"><table><thead><tr><th>{{ tx('月份','Month') }}</th><th>{{ tx('订单金额（营业额）','Order total (revenue)') }}</th><th>{{ tx('产品金额','Product') }}</th><th>{{ tx('安装','Installation') }}</th><th>GST</th><th>{{ tx('已收定金','Deposits received') }}</th><th>{{ tx('预计尾款（ETA）','Forecast balance (ETA)') }}</th></tr></thead><tbody><tr v-for="row in monthly" :key="row.month"><th>{{ monthLabel(row.month) }}</th><td>{{ amount(row.booked) }}</td><td>{{ amount(row.product) }}</td><td>{{ amount(row.installation) }}</td><td>{{ amount(row.gst) }}</td><td>{{ amount(row.received) }}</td><td>{{ amount(row.balance) }}</td></tr></tbody></table></div>
    </section>
    <section class="profit-area"><div><h2>{{ tx('每单利润','Profit per order') }}</h2><p>{{ tx('接入真实工厂成本、运费与关税后显示。','Will appear when real factory costs, freight and duties are available.') }}</p></div><span>{{ tx('等待成本数据','Awaiting cost data') }}</span></section>
  </main>
</template>

<style scoped>
.dashboard-live{display:grid;gap:12px;color:#344552}.dashboard-title,.section-title{display:flex;justify-content:space-between;align-items:center;gap:16px}.dashboard-title{padding:4px 0 10px;border-bottom:1px solid #d5dee3}.dashboard-title p{margin:0;color:#657784;font-size:10px;letter-spacing:.12em}.dashboard-title h1{margin:4px 0 0;font-size:23px}.dashboard-title button{border:1px solid #c5d1d8;border-radius:999px;background:white;padding:7px 12px;color:#344552}.task-area,.finance-area,.profit-area{padding:13px 15px;background:white;border:1px solid #dbe3e7;border-radius:10px}.task-area h2,.finance-area h2,.profit-area h2{margin:0;font-size:16px}.task-area>p,.section-title p,.profit-area p{color:#63737d;margin:4px 0 0;font-size:11px}.task-cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-top:10px}.task-card{display:grid;gap:8px;min-width:0;text-align:left;padding:11px;border:1px solid #d3dee4;border-radius:9px;background:#f8fafb;color:#344552}.task-card header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.task-card header>div{display:flex;align-items:center;gap:9px}.task-card span{font-weight:650}.task-card strong{font-size:20px;line-height:1.1;color:#405969}.task-card small{color:#657784;font-size:10px}.task-list{display:grid;max-height:195px;overflow:auto;border-top:1px solid #dfe6e9}.task-order{display:flex;align-items:center;gap:9px;min-height:40px;padding:6px 2px;border:0;border-bottom:1px solid #e7ecef;border-radius:0;background:transparent;color:#344552;text-align:left}.task-order:hover{background:#eef3f5;color:#344552;border-color:#d4dfe4}.task-order>strong{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.task-order>span{min-width:0;flex:1;overflow:hidden;color:#687984;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.task-order>b{flex:none;color:#3f657a;font-size:10px}.task-order-select{display:grid;grid-template-columns:20px minmax(0,1fr);cursor:pointer}.task-order-select input{width:16px;height:16px;accent-color:#425b6b}.task-order-select button{display:grid;min-width:0;gap:2px;padding:0;border:0;border-radius:0;background:transparent;color:#344552;text-align:left}.task-order-select button:hover{background:transparent;color:#344552}.task-order-select button strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px}.task-order-select button span{overflow:hidden;color:#687984;text-overflow:ellipsis;white-space:nowrap;font-size:10px}.task-empty{margin:0;padding:8px 2px;color:#788791;font-size:11px}.task-bulk{justify-self:end;min-height:34px;padding:5px 12px;border:1px solid #405b6b;border-radius:999px;background:#405b6b;color:#fff;font-size:11px}.task-bulk:disabled{opacity:.5}.dashboard-notice{padding:7px 10px;border-radius:6px;background:#e6f4ec;color:#216842}.finance-table-wrap{overflow-x:auto;margin-top:7px}.finance-area table{width:100%;min-width:670px;border-collapse:collapse}.finance-area th,.finance-area td{text-align:left;padding:5px 8px;border-bottom:1px solid #edf1f3;font-size:11px;font-variant-numeric:tabular-nums}.finance-area thead th{font-size:10px;color:#61717c}.finance-area tbody th{white-space:nowrap;color:#405462}.profit-area{display:flex;align-items:center;justify-content:space-between;gap:16px;background:#f8fafb}.profit-area>span{border:1px solid #d9e2e6;border-radius:999px;padding:5px 9px;font-size:11px;color:#64747e}.dashboard-error{padding:12px;background:#fae8e1;border-radius:8px;color:#842b16}.muted{color:#65756b}@media(max-width:680px){.task-cards{grid-template-columns:1fr}.task-area,.finance-area,.profit-area{padding:12px}.profit-area{align-items:flex-start;flex-direction:column}}
.dashboard-live{grid-template-columns:repeat(2,minmax(0,1fr));align-items:start}
.dashboard-title,.task-area,.dashboard-error{grid-column:1/-1}
.finance-area{grid-column:1;min-width:0}
.profit-area{grid-column:2;min-height:70px}
@media(max-width:850px){.dashboard-live{grid-template-columns:1fr}.dashboard-title,.task-area,.dashboard-error,.finance-area,.profit-area{grid-column:1}.finance-area{overflow:hidden}}
</style>
