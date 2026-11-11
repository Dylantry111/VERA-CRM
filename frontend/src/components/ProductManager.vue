<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { request } from '../crm-api';
import type { ApiProduct } from '../api';

const props = defineProps<{ admin: boolean }>();
const emit = defineEmits<{ updated: [] }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === 'zh' ? zh : en;
type Product = ApiProduct & { published: boolean; orderable?: boolean; product_category?: string; pricing_method?: 'per_sqm' | 'matrix'; pricing_matrix?: Record<string, Record<string, string>>; image_url?: string; image_urls?: string[]; unit?: 'mm' | 'inch'; colors?: string[]; controls?: string[] };
type Knowledge = { current?: { products?: any[]; order_minimum_area?: string | number; installation_per_panel?: string | number; minimum_installation?: string | number }; facts?: any[] };
const products = ref<Product[]>([]);
const categories = ref<string[]>(['Interior shutters', 'Interior blinds', 'Exterior shutters', 'Exterior blinds']);
const knowledge = ref<Knowledge>({});
const search = ref('');
const categoryFilter = ref('');
const selected = ref<Product | null>(null);
const adding = ref(false);
const categoryEditorOpen = ref(false);
const draftCategories = ref<string[]>([]);
const newCategory = ref('');
const busy = ref(false);
const loading = ref(true);
const error = ref('');
const notice = ref('');
const price = reactive({ rate_per_m2: '', minimum_area: '', order_minimum_area: '', installation_per_panel: '', minimum_installation: '' });
const form = reactive({ id: 0, name_en: '', material_en: '', product_category: 'Interior shutters', description_en: '', pricing_method: 'per_sqm' as 'per_sqm' | 'matrix', pricing_matrix: {} as Record<string, Record<string, string>>, published: false, orderable: false, sample: false });
const widths = Array.from({ length: 25 }, (_, index) => 600 + index * 100);
const heights = Array.from({ length: 20 }, (_, index) => 600 + index * 100);
const internalCategory = computed(() => form.product_category.toLowerCase().includes('blind') ? 'blinds' : 'shutters');
const visibleProducts = computed(() => products.value.filter(p => !(p.category === 'blinds' && !p.published && p.source_code)));
const filteredProducts = computed(() => visibleProducts.value.filter(p =>
  (!categoryFilter.value || (p.product_category || '').toLowerCase() === categoryFilter.value.toLowerCase()) &&
  `${p.name_en} ${p.material_en} ${p.product_category || ''}`.toLowerCase().includes(search.value.toLowerCase().trim())
));
const activeRule = (code?: string) => knowledge.value.current?.products?.find((row: any) => row.source_code === code);
const shutters = computed(() => internalCategory.value === 'shutters');
const priceChanged = computed(() => {
  const rule = activeRule(selected.value?.source_code);
  const current = knowledge.value.current;
  if (!rule || !current) return false;
  return String(rule.rate_per_m2 ?? '') !== price.rate_per_m2 || String(rule.minimum_area ?? '') !== price.minimum_area ||
    String(current.order_minimum_area ?? '') !== price.order_minimum_area || String(current.installation_per_panel ?? '') !== price.installation_per_panel ||
    String(current.minimum_installation ?? '') !== price.minimum_installation;
});

function fillPrice(product?: Product | null) {
  const rule = activeRule(product?.source_code);
  const current = knowledge.value.current;
  price.rate_per_m2 = String(rule?.rate_per_m2 ?? product?.['rate_per_m2' as keyof Product] ?? '');
  price.minimum_area = String(rule?.minimum_area ?? '0.5');
  price.order_minimum_area = String(current?.order_minimum_area ?? '1');
  price.installation_per_panel = String(current?.installation_per_panel ?? '');
  price.minimum_installation = String(current?.minimum_installation ?? '150');
}
function startEdit(product: Product) {
  selected.value = product; adding.value = false; error.value = ''; notice.value = '';
  Object.assign(form, { id: product.id, name_en: product.name_en || '', material_en: product.material_en || '', product_category: product.product_category || (product.category === 'blinds' ? 'Interior blinds' : 'Interior shutters'), description_en: product.description_en || '', pricing_method: product.pricing_method || (product.category === 'blinds' ? 'matrix' : 'per_sqm'), pricing_matrix: structuredClone(product.pricing_matrix || {}), published: !!product.published, orderable: !!product.orderable, sample: !!product.sample });
  fillPrice(product);
}
function startNew() {
  selected.value = null; adding.value = true; error.value = ''; notice.value = '';
  Object.assign(form, { id: 0, name_en: '', material_en: '', product_category: categories.value[0] || 'Interior shutters', description_en: '', pricing_method: 'per_sqm', pricing_matrix: {}, published: false, orderable: false, sample: false });
  fillPrice(null);
}
function closeEditor() { selected.value = null; adding.value = false; error.value = ''; notice.value = ''; }
function chooseCategory(value: string) {
  form.product_category = value;
  form.pricing_method = value.toLowerCase().includes('blind') ? 'matrix' : 'per_sqm';
  if (form.pricing_method === 'matrix' && !Object.keys(form.pricing_matrix).length) form.pricing_matrix = {};
}
function matrixValue(height: number, width: number) { return form.pricing_matrix[String(height)]?.[String(width)] || ''; }
function setMatrixValue(height: number, width: number, value: string) {
  if (!form.pricing_matrix[String(height)]) form.pricing_matrix[String(height)] = {};
  form.pricing_matrix[String(height)][String(width)] = value;
}
async function publishPricingChange() {
  const code = selected.value?.source_code;
  if (!code || !knowledge.value.current) return;
  const draft = await request<any>('operations/pricing-knowledge/drafts/from-current', {});
  const productRule = draft.manifest.products?.find((row: any) => row.source_code === code);
  if (!productRule) throw new Error(tx('该产品没有连接到现有报价规则。','This product is not linked to an active quote rule.'));
  productRule.rate_per_m2 = Number(price.rate_per_m2);
  productRule.minimum_area = Number(price.minimum_area);
  draft.manifest.order_minimum_area = Number(price.order_minimum_area);
  draft.manifest.installation_per_panel = Number(price.installation_per_panel);
  draft.manifest.minimum_installation = Number(price.minimum_installation);
  await request(`operations/pricing-knowledge/drafts/${encodeURIComponent(draft.id)}`, { manifest: draft.manifest, facts: draft.facts });
  await request(`operations/pricing-knowledge/drafts/${encodeURIComponent(draft.id)}/publish`, {});
}
async function saveProduct() {
  if (!props.admin) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    if (!form.name_en.trim() || !form.material_en.trim() || !form.product_category) throw new Error(tx('请填写英文名称、材质和种类。','Enter the English name, material and category.'));
    if (shutters.value && (!Number.isFinite(Number(price.rate_per_m2)) || Number(price.rate_per_m2) <= 0)) throw new Error(tx('请填写有效的每平方米单价。','Enter a valid rate per square metre.'));
    if (shutters.value && (!Number.isFinite(Number(price.minimum_area)) || Number(price.minimum_area) <= 0 || !Number.isFinite(Number(price.order_minimum_area)) || Number(price.order_minimum_area) <= 0 || !Number.isFinite(Number(price.installation_per_panel)) || !Number.isFinite(Number(price.minimum_installation)))) throw new Error(tx('请检查面积和安装费规则。','Check the area and installation rules.'));
    if (priceChanged.value) await publishPricingChange();
    const payload = {
      name_en: form.name_en.trim(), name_zh: form.name_en.trim(), material_en: form.material_en.trim(), material_zh: form.material_en.trim(),
      description_en: form.description_en.trim(), description_zh: form.description_en.trim(), category: internalCategory.value,
      product_category: form.product_category, pricing_method: form.pricing_method, pricing_matrix: form.pricing_matrix,
      published: form.published, orderable: form.orderable, sample: form.sample,
      image_url: selected.value?.image_url || '', image_urls: selected.value?.image_urls || [], unit: selected.value?.unit || 'mm',
      width_min: null, width_max: null, height_min: null, height_max: null, colors: selected.value?.colors || [], controls: selected.value?.controls || [],
    };
    await request<Product>(selected.value ? `admin/products/${form.id}` : 'admin/products', payload);
    await load(); emit('updated'); notice.value = tx('产品已保存。新价格只影响之后创建的订单。','Product saved. New prices apply only to orders created from now on.');
    const saved = products.value.find(p => p.id === form.id);
    if (!adding.value && saved) startEdit(saved); else closeEditor();
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
function openCategoryEditor() { draftCategories.value = [...categories.value]; newCategory.value = ''; categoryEditorOpen.value = true; }
function addCategory() { const value = newCategory.value.trim(); if (!value || draftCategories.value.some(item => item.toLowerCase() === value.toLowerCase())) return; draftCategories.value.push(value); newCategory.value = ''; }
function removeCategory(value: string) { draftCategories.value = draftCategories.value.filter(item => item !== value); }
async function saveCategories() {
  busy.value = true; error.value = '';
  try { const result = await request<{ categories: string[] }>('operations/product-categories', { categories: draftCategories.value }); categories.value = result.categories; categoryEditorOpen.value = false; }
  catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
async function load() {
  loading.value = true;
  try {
    const tasks: Promise<any>[] = [request<Product[]>('admin/products')];
    if (props.admin) tasks.push(request<{ categories: string[] }>('operations/product-categories'), request<Knowledge>('operations/pricing-knowledge'));
    const result = await Promise.all(tasks);
    products.value = result[0].map((p: Product) => ({ ...p, product_category: p.product_category || (p.category === 'blinds' ? 'Interior blinds' : 'Interior shutters') }));
    if (props.admin) { categories.value = result[1].categories; knowledge.value = result[2]; }
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { loading.value = false; }
}
onMounted(load);
</script>

<template>
  <section class="product-admin">
    <header class="product-head"><div><p class="eyebrow">VERA · PRODUCT CATALOGUE</p><h2>Products</h2><p>Manage product details and the pricing rules used for future quotes.</p></div><div class="toolbar"><input v-model="search" type="search" placeholder="Search products" /><select v-model="categoryFilter"><option value="">All categories</option><option v-for="category in categories" :key="category" :value="category">{{ category }}</option></select><button v-if="admin" type="button" class="secondary" @click="openCategoryEditor">Manage categories</button><button v-if="admin" type="button" class="primary" @click="startNew">＋ Add product</button></div></header>
    <p v-if="error && !selected && !categoryEditorOpen" class="alert">{{ error }}</p><p v-if="notice && !selected" class="success">{{ notice }}</p>
    <div v-if="loading" class="empty">Loading products…</div>
    <div v-else-if="filteredProducts.length" class="product-table-wrap"><table class="product-table"><thead><tr><th>Display name</th><th>Material</th><th>Category</th><th>Pricing</th><th>Website</th><th></th></tr></thead><tbody><tr v-for="product in filteredProducts" :key="product.id"><td><strong>{{ product.name_en }}</strong><small>#{{ product.id }}</small></td><td>{{ product.material_en }}</td><td>{{ product.product_category }}</td><td>{{ product.pricing_method === 'matrix' ? 'Width × height matrix' : 'Area · per m²' }}</td><td>{{ product.published ? 'Published' : 'Hidden' }}</td><td><button type="button" class="row-edit" @click="startEdit(product)">{{ admin ? 'Edit' : 'View' }}</button></td></tr></tbody></table></div>
    <div v-else class="empty">No products found.</div>

    <div v-if="selected || adding" class="shade" @click.self="closeEditor"><section class="editor" role="dialog" aria-modal="true" aria-label="Product details"><header><div><p class="eyebrow">PRODUCT DETAILS</p><h3>{{ adding ? 'Add product' : form.name_en }}</h3></div><button type="button" class="icon" @click="closeEditor">×</button></header><form @submit.prevent="saveProduct">
      <div class="fields"><label>Display name<input v-model="form.name_en" maxlength="160" required :readonly="!admin" /></label><label>Material<input v-model="form.material_en" maxlength="100" required :readonly="!admin" /></label><label>Category<select :value="form.product_category" :disabled="!admin" @change="chooseCategory(($event.target as HTMLSelectElement).value)"><option v-for="category in categories" :key="category">{{ category }}</option></select></label><label>Description<textarea v-model="form.description_en" maxlength="3000" rows="3" :readonly="!admin" /></label></div>
      <section class="pricing"><h4>Pricing & calculation</h4><template v-if="shutters"><div class="fields pricing-fields"><label>Product price per m² (NZD)<input v-model="price.rate_per_m2" inputmode="decimal" :readonly="!admin" /></label><label>Minimum billable area per window (m²)<input v-model="price.minimum_area" inputmode="decimal" :readonly="!admin" /></label><label>Order minimum area (m²)<input v-model="price.order_minimum_area" inputmode="decimal" :readonly="!admin" /></label><label>Installation per panel (NZD)<input v-model="price.installation_per_panel" inputmode="decimal" :readonly="!admin" /></label><label>Minimum installation per order (NZD)<input v-model="price.minimum_installation" inputmode="decimal" :readonly="!admin" /></label></div><p class="hint">Window area is rounded up to 0.01 m². The per-window floor and order-wide minimum are applied separately. Installation is calculated from panel count.</p></template><template v-else><p class="hint">Prices are looked up by window size. Widths: 600–3000 mm. Heights: 600–2500 mm. Both axes advance in 100 mm steps.</p><div v-if="admin" class="matrix-scroll"><table class="matrix"><thead><tr><th>Drop / Width</th><th v-for="width in widths" :key="width">{{ width }}</th></tr></thead><tbody><tr v-for="height in heights" :key="height"><th>{{ height }}</th><td v-for="width in widths" :key="width"><input inputmode="decimal" :aria-label="`Price at ${width} by ${height} mm`" :value="matrixValue(height,width)" @input="setMatrixValue(height,width,($event.target as HTMLInputElement).value)" /></td></tr></tbody></table></div><p v-else class="hint">Matrix prices are not configured.</p></template></section>
      <div v-if="admin" class="publish-options"><label><input v-model="form.published" type="checkbox" /> Show on website</label><label><input v-model="form.orderable" type="checkbox" /> Available for new orders</label></div>
      <p v-if="error" class="alert">{{ error }}</p><p v-if="notice" class="success">{{ notice }}</p><footer><button v-if="admin" type="submit" class="primary" :disabled="busy">{{ busy ? 'Saving…' : 'Save product' }}</button><button type="button" class="secondary" @click="closeEditor">{{ admin ? 'Cancel' : 'Close' }}</button></footer>
    </form></section></div>

    <div v-if="categoryEditorOpen" class="shade" @click.self="categoryEditorOpen=false"><section class="category-editor" role="dialog" aria-modal="true" aria-label="Manage product categories"><header><div><p class="eyebrow">PRODUCT SETTINGS</p><h3>Manage categories</h3></div><button type="button" class="icon" @click="categoryEditorOpen=false">×</button></header><p>Categories group products and determine their pricing method. Categories assigned to a product cannot be removed.</p><div class="category-list"><div v-for="category in draftCategories" :key="category"><span>{{ category }}</span><button type="button" class="remove-category" @click="removeCategory(category)" :disabled="products.some(p => p.product_category === category)">Remove</button></div></div><div class="category-add"><input v-model="newCategory" maxlength="80" placeholder="New category name" @keydown.enter.prevent="addCategory" /><button type="button" class="secondary" @click="addCategory">Add</button></div><p v-if="error" class="alert">{{ error }}</p><footer><button type="button" class="primary" :disabled="busy || draftCategories.length < 4" @click="saveCategories">{{ busy ? 'Saving…' : 'Save categories' }}</button><button type="button" class="secondary" @click="categoryEditorOpen=false">Cancel</button></footer></section></div>
  </section>
</template>

<style scoped>
.product-admin{color:#1b2421}.product-head{display:flex;align-items:flex-end;justify-content:space-between;gap:18px;flex-wrap:wrap;margin:4px 0 16px}.product-head h2{margin:0;font-size:24px}.product-head p:not(.eyebrow){margin:5px 0 0;color:#627168;font-size:13px}.eyebrow{margin:0 0 4px;font-size:10px;letter-spacing:.12em;color:#64766b}.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.toolbar input,.toolbar select,.fields input,.fields select,.fields textarea,.category-add input{box-sizing:border-box;min-height:38px;padding:7px 10px;border:1px solid #cdd8d0;border-radius:6px;background:#fff;font:inherit}.toolbar input{width:210px}.toolbar select{min-width:170px}.primary,.secondary,.row-edit,.icon{min-height:38px;padding:0 14px;border-radius:999px;border:1px solid #0f6e5c;background:#0f6e5c;color:#fff;font-weight:650;cursor:pointer}.secondary,.row-edit{border-color:#cdd8d0;background:#fff;color:#284537}.product-table-wrap{overflow:auto;background:#fff;border:1px solid #e1e7e2;border-radius:8px}.product-table{width:100%;border-collapse:collapse}.product-table th,.product-table td{padding:11px 12px;border-bottom:1px solid #edf0ed;text-align:left;font-size:13px;white-space:nowrap}.product-table th{color:#52635a;font-size:11px;letter-spacing:.03em}.product-table tbody tr:hover{background:#f8faf8}.product-table td:first-child{white-space:normal}.product-table td small{display:block;color:#758279;font-size:11px}.empty{padding:32px;color:#718078}.shade{position:fixed;inset:0;z-index:1100;display:grid;place-items:center;padding:16px;background:#10251b77}.editor,.category-editor{width:min(850px,96vw);max-height:92dvh;overflow:auto;background:#f7f9f7;border-radius:12px;box-shadow:0 18px 56px #10251b55}.editor>header,.category-editor>header{position:sticky;top:0;z-index:1;display:flex;justify-content:space-between;align-items:flex-start;padding:18px 22px;background:white;border-bottom:1px solid #e1e8e2}.editor h3,.category-editor h3{margin:0;font-size:20px}.icon{width:38px;min-width:38px;padding:0;background:white;color:#385347;border-color:#d7e0d9;font-size:20px}.editor form{padding:18px 22px}.fields{display:grid;grid-template-columns:1fr 1fr;gap:12px}.fields label{display:grid;gap:5px;font-size:12px;font-weight:650;color:#43574b}.fields label:last-child{grid-column:1/-1}.fields textarea{resize:vertical}.pricing{margin-top:18px;padding:15px;background:white;border:1px solid #dfe7e1;border-radius:8px}.pricing h4{margin:0 0 12px;font-size:15px}.pricing-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.hint{font-size:12px;color:#627168;line-height:1.55}.publish-options{display:flex;gap:20px;flex-wrap:wrap;margin-top:14px;font-size:13px}.publish-options label{display:flex;align-items:center;gap:7px}.editor footer,.category-editor footer{display:flex;gap:8px;justify-content:flex-end;padding-top:16px}.matrix-scroll{overflow:auto;max-height:360px;border:1px solid #e4eae5}.matrix{border-collapse:collapse;width:max-content;font-size:10px}.matrix th,.matrix td{padding:3px;border:1px solid #e5eae6;text-align:center}.matrix th{position:sticky;top:0;background:#f1f5f2}.matrix input{width:66px;min-height:29px;padding:3px 5px;border:1px solid #d6ded7;border-radius:4px}.category-editor{width:min(520px,96vw);padding-bottom:18px}.category-editor>p{padding:0 20px;color:#627168;font-size:13px;line-height:1.5}.category-list{display:grid;gap:6px;padding:0 20px}.category-list>div{display:flex;align-items:center;justify-content:space-between;padding:8px 10px;background:#fff;border:1px solid #e2e8e3;border-radius:6px}.remove-category{border:0;background:transparent;color:#8c3d34;font-size:12px;cursor:pointer}.remove-category:disabled{opacity:.35;cursor:not-allowed}.category-add{display:flex;gap:8px;padding:12px 20px}.category-add input{flex:1}.category-editor footer{padding:0 20px}.alert,.success{padding:10px 12px;border-radius:6px;font-size:13px;background:#fff0ed;color:#8f3425}.success{background:#edf5ef;color:#17523a}@media(max-width:700px){.toolbar{width:100%}.toolbar input,.toolbar select{width:100%}.fields,.pricing-fields{grid-template-columns:1fr}.fields label:last-child{grid-column:auto}.editor>header,.editor form{padding-inline:14px}}
</style>
