<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { listProducts, type ApiProduct } from "../api";

interface TradePrice { product_id: number; name: string; material: string; rate_per_sqm: string | null; price_available: boolean; minimum_sqm_per_item: string; options: Record<string, Record<string, Record<string, string>>> }
interface PriceBook { configured: boolean; currency: string; gst_rate: string; deposit_rate: string; minimum_sqm_per_order: string; addons?: any[]; products: TradePrice[] }
const route = useRoute();
const router = useRouter();
const products = ref<ApiProduct[]>([]);
const pricing = ref<PriceBook | null>(null);
const loading = ref(true);
const priceError = ref("");
const dialog = ref<HTMLDialogElement | null>(null);
const sending = ref(false);
const error = ref("");
const receipt = ref("");
const draft = reactive({
  company_name: "", nzbn: "", primary_contact_name: "", primary_email: "", primary_phone: "",
  finance_email: "", finance_phone: "", company_address: "", notes: "",
  monthly_sqm: {} as Record<number, string>,
});
const selected = computed(() => products.value.filter((product) => draft.monthly_sqm[product.id]));
const formatMoney = (amount: string, currency = "NZD") => new Intl.NumberFormat("en-NZ", { style: "currency", currency }).format(Number(amount));
const percent = (value: string | undefined) => `${(Number(value || 0) * 100).toFixed(0)}%`;
const addonPrices = computed(() => (pricing.value?.addons || []).flatMap((addon: any) => (addon.choices || []).map((choice: any) => {
  const charges = [choice.fixed !== undefined ? `${formatMoney(String(choice.fixed))} fixed` : "", choice.per_sqm !== undefined ? `${formatMoney(String(choice.per_sqm))}/m²` : "", choice.percent !== undefined ? `${choice.percent}%` : ""].filter(Boolean);
  return charges.length ? `${addon.label_en || addon.key} — ${choice.label_en || choice.value}: ${charges.join(" · ")}` : "";
}).filter(Boolean)));
function optionPriceNotes(options: TradePrice["options"]) {
  return Object.entries(options || {}).flatMap(([name, choices]) => Object.entries(choices || {}).map(([choice, charges]) => {
    const values = Object.entries(charges || {}).filter(([, amount]) => Number(amount) !== 0)
      .map(([kind, amount]) => `${kind.replace("per_sqm", "/m²").replace("fixed", "fixed").replace("percent", "%")}: ${formatMoney(amount)}`);
    return `${name.replaceAll("_", " ")} — ${choice}${values.length ? ` (${values.join(", ")})` : ""}`;
  }));
}
function openForm() {
  error.value = "";
  receipt.value = "";
  dialog.value?.showModal();
}
function closeForm() {
  dialog.value?.close();
  if (route.query.apply) void router.replace({ query: { ...route.query, apply: undefined } });
}
watch(() => route.query.apply, (value) => { if (value === "1" && dialog.value && !dialog.value.open) openForm(); });
async function submit() {
  error.value = "";
  if (!selected.value.length) { error.value = "Select at least one product and enter its estimated monthly area."; return; }
  sending.value = true;
  try {
    const response = await fetch("/api/trade-applications", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        company_name: draft.company_name, nzbn: draft.nzbn, primary_contact_name: draft.primary_contact_name,
        primary_email: draft.primary_email, primary_phone: draft.primary_phone, finance_email: draft.finance_email,
        finance_phone: draft.finance_phone, company_address: draft.company_address, notes: draft.notes,
        product_interests: selected.value.map((product) => ({ product_id: product.id, monthly_sqm: draft.monthly_sqm[product.id] })),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Your application could not be submitted.");
    receipt.value = data.reference;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { sending.value = false; }
}
onMounted(async () => {
  try {
    const [catalogue, response] = await Promise.all([listProducts(), fetch("/api/public/trade-pricing")]);
    products.value = catalogue;
    if (!response.ok) throw new Error("The trade price list is temporarily unavailable.");
    pricing.value = await response.json();
  } catch (cause) { priceError.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; if (route.query.apply === "1") dialog.value?.showModal(); }
});
</script>

<template>
  <main class="trade-page">
    <header class="hero"><p class="eyebrow">VERA / TRADE ACCOUNTS</p><h1>Trade pricing, terms<br />and account applications</h1><p>Clear product pricing and payment steps for New Zealand trade customers.</p><button type="button" class="primary" @click="openForm">Apply for a Trade Account</button></header>
    <section class="content price-section"><div class="section-heading"><div><p class="eyebrow">CURRENT PRICE LIST</p><h2>Wholesale product pricing</h2></div><p>Base product rates in NZD per square metre. Final quotes reflect measured dimensions and selected options.</p></div>
      <p v-if="loading" class="notice">Loading current prices…</p><p v-else-if="priceError" class="notice error">{{ priceError }}</p><p v-else-if="!pricing?.products.length" class="notice">Current prices are being updated. Contact VERA for a quote.</p>
      <div v-else class="price-table-wrap"><table><thead><tr><th>Product range</th><th>Material</th><th>Base rate</th><th>Minimum area per item</th><th>Price options</th></tr></thead><tbody><tr v-for="item in pricing.products" :key="item.product_id"><td><strong>{{ item.name }}</strong></td><td>{{ item.material }}</td><td>{{ item.price_available ? `${formatMoney(item.rate_per_sqm || '0')} / m²` : "Contact VERA" }}</td><td>{{ item.minimum_sqm_per_item }} m²</td><td><details v-if="optionPriceNotes(item.options).length"><summary>View option rates</summary><ul><li v-for="note in optionPriceNotes(item.options)" :key="note">{{ note }}</li></ul></details><span v-else>Quoted by specification</span></td></tr></tbody></table></div>
      <p v-if="pricing?.configured" class="price-note">Minimum order area: {{ pricing.minimum_sqm_per_order }} m². GST: {{ percent(pricing.gst_rate) }} is added to the quoted total. Pricing is based on the currently published VERA price rules.</p>
      <details v-if="addonPrices.length" class="addon-prices"><summary>View available add-on rates</summary><ul><li v-for="entry in addonPrices" :key="entry">{{ entry }}</li></ul></details>
    </section>
    <section class="content terms-section"><p class="eyebrow">HOW TRADE ORDERS WORK</p><h2>Order and payment terms</h2><div class="steps"><article><span>01</span><h3>Apply for an account</h3><p>Submit your company and contact details with the product ranges and monthly area you expect to purchase. Applications are reviewed by VERA.</p></article><article><span>02</span><h3>Receive your trade login</h3><p>Once approved, your portal login is created and your application details are saved in My Profile.</p></article><article><span>03</span><h3>Confirm the order with a 60% deposit</h3><p>Configure products and sizes in the portal. After VERA reviews the order, a 60% deposit invoice is issued. The deposit must be paid for the order to be placed.</p></article><article><span>04</span><h3>Pay the balance before collection</h3><p>The remaining 40% is due before goods are collected. For orders with installation, the balance is due before installation begins.</p></article></div><p class="terms-note">There is no credit-check step. Orders are released for collection or installation after the account is settled in full. Product lead times are confirmed with each order.</p><aside class="rebate-note"><strong>Monthly trade rebate</strong><span>When product totals for a calendar month exceed NZD $10,000, the customer earns a 5% rebate on that month’s product total. The deposit paid date determines the month; unused totals do not carry forward.</span></aside><button type="button" class="secondary" @click="openForm">Apply for a Trade Account</button></section>

    <dialog ref="dialog" class="application-dialog" aria-labelledby="application-title" @click="(event) => { if (event.target === dialog) closeForm(); }">
      <div class="dialog-content"><header class="dialog-head"><div><p class="eyebrow">TRADE ACCOUNT APPLICATION</p><h2 id="application-title">Apply for a Trade Account</h2><p>Complete the company, contact and monthly product estimates below.</p></div><button type="button" class="close" aria-label="Close application" @click="closeForm">×</button></header>
        <div v-if="receipt" class="success-state"><strong>Application received</strong><p>Your reference is <b>{{ receipt }}</b>. VERA will review your application and email the primary contact when the account is approved.</p><button type="button" class="primary" @click="closeForm">Close</button></div>
        <form v-else class="application-form" @submit.prevent="submit">
          <fieldset><legend>Company information</legend><label>Full legal company name *<input v-model.trim="draft.company_name" required maxlength="200" autocomplete="organization" /></label><label>New Zealand Business Number (NZBN) *<input v-model.trim="draft.nzbn" required inputmode="numeric" pattern="[0-9]{13}" minlength="13" maxlength="13" placeholder="13 digits" /></label><label class="wide">Company address *<input v-model.trim="draft.company_address" required maxlength="1000" autocomplete="street-address" /></label></fieldset>
          <fieldset><legend>Main contact</legend><label>Contact name *<input v-model.trim="draft.primary_contact_name" required maxlength="200" autocomplete="name" /></label><label>Phone *<input v-model.trim="draft.primary_phone" required type="tel" maxlength="100" autocomplete="tel" /></label><label class="wide">Email *<input v-model.trim="draft.primary_email" required type="email" maxlength="200" autocomplete="email" /></label></fieldset>
          <fieldset><legend>Finance contact</legend><label>Finance email *<input v-model.trim="draft.finance_email" required type="email" maxlength="200" /></label><label>Finance phone *<input v-model.trim="draft.finance_phone" required type="tel" maxlength="100" /></label></fieldset>
          <fieldset><legend>Product interest and monthly estimate *</legend><p class="fieldset-hint">Select the ranges you expect to buy and estimate the monthly area for each, in square metres.</p><div class="interest-grid"><div v-for="product in products" :key="product.id" class="interest-row"><label class="check"><input v-model="draft.monthly_sqm[product.id]" type="checkbox" true-value="1" false-value="" /><span><strong>{{ product.name_en }}</strong><small>{{ product.material_en }}</small></span></label><label class="sqm">m² / month<input v-model="draft.monthly_sqm[product.id]" type="number" min="0.1" step="0.1" placeholder="e.g. 20" /></label></div></div></fieldset>
          <label class="notes">Additional information (optional)<textarea v-model.trim="draft.notes" rows="3" maxlength="2000" placeholder="Anything else you would like VERA to know" /></label>
          <p class="privacy">Your information will be used to review this trade account application and create the account profile if approved. We do not conduct credit checks.</p>
          <p v-if="error" class="error" role="alert">{{ error }}</p><footer><button type="button" class="secondary" @click="closeForm">Cancel</button><button type="submit" class="primary" :disabled="sending">{{ sending ? "Submitting…" : "Submit application" }}</button></footer>
        </form>
      </div>
    </dialog>
  </main>
</template>

<style scoped>
.trade-page{color:#28343a;background:#fafbfa}.hero{padding:clamp(48px,8vw,96px) clamp(24px,8vw,120px);background:#edf1f2;border-bottom:1px solid #d9e0e2}.eyebrow{margin:0 0 10px;color:#5f727d;font-size:10px;font-weight:750;letter-spacing:.15em}.hero h1{max-width:780px;margin:0;font:600 clamp(36px,5vw,62px)/1.08 var(--font-display)}.hero>p:not(.eyebrow){margin:16px 0 22px;color:#586a73;font-size:15px}.primary,.secondary{min-height:42px;padding:10px 16px;border:1px solid #435a67;border-radius:5px;background:#435a67;color:#fff;font:600 13px inherit;cursor:pointer}.secondary{background:#fff;color:#435a67}.primary:hover{background:#344a56}.content{max-width:1200px;margin:0 auto;padding:50px clamp(22px,5vw,68px)}.section-heading{display:flex;justify-content:space-between;align-items:end;gap:24px;margin-bottom:18px}.section-heading h2,.terms-section h2{margin:0;font:600 28px var(--font-display)}.section-heading>p{max-width:450px;color:#5c6b73;font-size:13px;line-height:1.6}.price-table-wrap{overflow:auto;border:1px solid #d7e0e2;border-radius:6px;background:#fff}table{width:100%;min-width:760px;border-collapse:collapse;text-align:left}th,td{padding:13px 15px;border-bottom:1px solid #e5eaeb;font-size:13px}th{background:#f1f4f4;color:#556972;font-size:10px;letter-spacing:.06em;text-transform:uppercase}tbody tr:last-child td{border-bottom:0}td strong{color:#293c46}details summary{cursor:pointer;color:#435a67;font-size:12px}details ul{min-width:180px;padding-left:16px;color:#586a73;font-size:11px}.price-note,.terms-note{color:#5b6b73;font-size:12px;line-height:1.7}.notice{padding:16px;background:#f0f3f3;color:#596b73}.error{color:#9c352d}.terms-section{border-top:1px solid #dce3e4}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.steps article{padding:17px;border:1px solid #d9e1e2;background:#fff;border-radius:6px}.steps article>span{color:#647c88;font-size:11px;font-weight:700}.steps h3{margin:12px 0 6px;font-size:15px}.steps p{margin:0;color:#5d6d74;font-size:12px;line-height:1.65}.terms-note{padding:14px;background:#edf1f2}.application-dialog{width:min(820px,calc(100vw - 28px));max-height:min(92dvh,900px);padding:0;border:1px solid #ccd7da;border-radius:9px;box-shadow:0 18px 58px #182b3538}.application-dialog::backdrop{background:#17293177}.dialog-content{padding:24px 28px}.dialog-head{display:flex;justify-content:space-between;gap:18px;margin-bottom:20px}.dialog-head h2{margin:0;font:600 27px var(--font-display)}.dialog-head p:not(.eyebrow){margin:5px 0;color:#62727a;font-size:12px}.close{width:36px;height:36px;border:0;border-radius:50%;background:#edf1f2;color:#344b55;font-size:24px;cursor:pointer}.application-form{display:grid;gap:16px}.application-form fieldset{display:grid;grid-template-columns:1fr 1fr;gap:12px 14px;margin:0;padding:14px;border:1px solid #dce3e4;border-radius:6px}.application-form legend{padding:0 6px;font-size:13px;font-weight:700;color:#394f59}.application-form label{display:grid;gap:5px;color:#4b5f68;font-size:11px;font-weight:650}.application-form input:not([type=checkbox]),.application-form textarea{width:100%;box-sizing:border-box;min-height:38px;padding:8px 10px;border:1px solid #cad5d8;border-radius:4px;background:#fff;font:400 13px inherit}.application-form .wide{grid-column:1/-1}.fieldset-hint{grid-column:1/-1;margin:0;color:#65767d;font-size:11px}.interest-grid{grid-column:1/-1;display:grid;gap:6px}.interest-row{display:grid;grid-template-columns:1fr 135px;align-items:center;gap:16px;padding:8px;border-bottom:1px solid #e9eeee}.application-form label.check{display:flex;align-items:center;gap:9px}.check input{width:17px;height:17px;accent-color:#435a67}.check span{display:grid}.check small{color:#77858b;font-weight:400}.sqm input{min-height:32px!important}.notes{display:grid;gap:5px;color:#4b5f68;font-size:11px}.application-form .privacy{margin:0;color:#65767d;font-size:11px;line-height:1.6}.application-form footer{display:flex;justify-content:flex-end;gap:8px}.success-state{padding:24px;border:1px solid #d6e5da;background:#f2f8f3;border-radius:6px;color:#334c3a}.success-state strong{font-size:18px}.success-state p{line-height:1.7}.success-state button{margin-top:8px}@media(max-width:760px){.steps{grid-template-columns:1fr 1fr}.section-heading{display:block}.content{padding-top:34px}.dialog-content{padding:18px}.application-form fieldset{grid-template-columns:1fr}.application-form .wide{grid-column:auto}.interest-row{grid-template-columns:1fr 110px}}@media(max-width:480px){.steps{grid-template-columns:1fr}.application-dialog{width:100vw;max-height:100dvh;height:100dvh;margin:0;border-radius:0}.dialog-content{max-height:100%;overflow:auto}.application-form footer{justify-content:space-between}}
.primary,.secondary{font:inherit;font-size:13px;font-weight:600}.addon-prices{margin-top:12px;color:#435a67;font-size:12px}.addon-prices summary{cursor:pointer}.addon-prices ul{max-height:230px;overflow:auto;padding-left:20px;line-height:1.7}.rebate-note{display:grid;gap:5px;margin:14px 0 20px;padding:14px 16px;border-left:3px solid #627c88;background:#f0f4f5;color:#53656e;font-size:12px;line-height:1.6}.rebate-note strong{color:#344b56}
</style>
