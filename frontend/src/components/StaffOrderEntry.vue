<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { request } from '../crm-api';
import { describeConfiguredAddons, isTrackAddon, syncOpeningStyle, trackAddonsLocked, type Addon } from '../addons';
import { Copy, Plus, SlidersHorizontal, Trash2 } from 'lucide-vue-next';

const emit = defineEmits<{ created: [] }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === 'zh' ? zh : en;
type Customer = { customer_id: number; company: string; customer_code?: string; contact_name?: string; email?: string };
type Product = { id: number; source_code: string; name_en?: string; name_zh?: string; material?: string; category?: string; orderable?: boolean; required_fields?: string[]; configuration_schema?: any[] };
type EntryLine = { window_name: string; product_id: number | ''; width_mm: string; height_mm: string; quantity: number; panel_count: number; options: Record<string,string> };
type OrderDraft = { ref: string; customer_id: number | ''; project_name: string; end_customer_name?: string; site_address: string; installation_required: boolean; lines: EntryLine[]; submit: boolean; historical_confirmed_deposit_date?: string };
type Preview = { customer_id: number; project_name: string; subtotal: string; installation?: string; tax: string; total: string; deposit: string; currency?: string; line_count: number };
const customers = ref<Customer[]>([]);
const products = ref<Product[]>([]);
const addons = ref<Addon[]>([]);
const mode = ref<'single'|'bulk'>('single');
const busy = ref(false);
const error = ref('');
const notice = ref('');
const pasted = ref('');
const previews = ref<Preview[]>([]);
const readyOrders = ref<OrderDraft[]>([]);
const preparedPayloads = ref<any[]>([]);
const draft = reactive<OrderDraft>({ ref: 'single', customer_id: '', project_name: '', end_customer_name: '', site_address: '', installation_required: false, lines: [], submit: false });
const bulkHeaders = ['Order Ref','Customer Code','Project Name','End Customer Name (optional)','Site Address','Installation Required','Window Name','Series','Width (mm)','Height (mm)','Quantity','Panels','Options JSON','Quote Date (YYYY-MM-DD)'];
const historicalImport = ref(false);
const BASE_REQUIRED_FIELDS = new Set(['window_name','width_mm','height_mm','product_id']);
const CURRENT_PANEL_REQUIRED_CODES = new Set(['Shutters_PVC_Eco','Shutters_PVC','Shutters_Pinewood','Shutters_Basswood','VERA_Ashwood_provisional']);
const DEFAULTED_FIELDS = ['opening_style','frame','louver_size','colour','control_rod','fitting'];
const addonDialog = ref<HTMLDialogElement|null>(null);
const addonTarget = ref<{line:EntryLine;index:number}|null>(null);
const headerText = computed(() => bulkHeaders.join('\t'));
watch(draft, () => clearPreview(), { deep: true });
const productLabel = (p: Product) => [p.material, locale.value === 'zh' ? p.name_zh : p.name_en].filter(Boolean).join(' · ') || p.source_code;
const customerLabel = (c: Customer) => `${c.customer_code ? `${c.customer_code} · ` : ''}${c.company}${c.contact_name ? ` · ${c.contact_name}` : ''}`;
const product = (id:number|'') => products.value.find(p=>Number(p.id)===Number(id));
function schemaFields(id:number|'') { return product(id)?.configuration_schema || []; }
function isTrackFrameStyle(line:EntryLine) { return ['tracked by fold','tracked bifold','tracked sliding'].includes(String(line.options.opening_style||'').trim().toLowerCase().replace(/\s+/g,' ')); }
function isRequired(line:EntryLine,key:string) {
  if (BASE_REQUIRED_FIELDS.has(key)) return true;
  const selected=product(line.product_id);
  if (key==='panel_count') return selected?.required_fields ? selected.required_fields.includes(key) : CURRENT_PANEL_REQUIRED_CODES.has(selected?.source_code||'');
  if (selected?.category==='shutters' && ['opening_style','layout_code'].includes(key)) return true;
  if (key==='vt_post') return /t/i.test(String(line.options.layout_code||''));
  if (key==='midrail') return Number(line.height_mm)>1500;
  if (key==='frame' && isTrackFrameStyle(line)) return true;
  return schemaFields(line.product_id).some(f=>f.key===key&&f.required===true);
}
function choicesFor(line:EntryLine,key:string):string[] { return schemaFields(line.product_id).find(f=>f.key===key)?.choices||[]; }
function fieldLabel(key:string) { const field=schemaFields(draft.lines[0]?.product_id||'').find(f=>f.key===key); return field ? (locale.value==='zh'?field.label_zh:field.label_en) : key.replaceAll('_',' '); }
function availableAddons(line:EntryLine) { return addons.value.filter(a=>!a.exclude?.includes(product(line.product_id)?.source_code||'')); }
function applyProductDefaults(line:EntryLine) {
  const allowed=new Map<string,any>(schemaFields(line.product_id).map(f=>[f.key,f]));
  const excluded=new Set(addons.value.filter(a=>a.exclude?.includes(product(line.product_id)?.source_code||'')).map(a=>a.key));
  for (const [key,value] of Object.entries(line.options)) { const f=allowed.get(key); if(excluded.has(key)||(f?.choices?.length&&value&&!f.choices.includes(value))||(!f&&!addons.value.some(a=>a.key===key))) delete line.options[key]; }
  for(const key of DEFAULTED_FIELDS){const f=allowed.get(key);if(f?.choices?.length&&!f.choices.includes(line.options[key]))line.options[key]=f.choices[0];}
  syncOpeningStyle(line.options);
  if(isTrackFrameStyle(line))line.options.frame='Track System'; else if(line.options.frame==='Track System')delete line.options.frame;
}
function onProductChange(line:EntryLine){applyProductDefaults(line);clearPreview();}
function onOpeningStyleChange(line:EntryLine){syncOpeningStyle(line.options);if(isTrackFrameStyle(line))line.options.frame='Track System';else if(line.options.frame==='Track System')delete line.options.frame;}
function newLine(): EntryLine { const line:EntryLine={ window_name:'', product_id:products.value.find(p=>p.orderable)?.id||'', width_mm:'', height_mm:'', quantity:1, panel_count:1, options:{} }; applyProductDefaults(line); return line; }
function addLine() { draft.lines.push(newLine()); }
function copyLine(line:EntryLine){draft.lines.push({...line,window_name:'',options:{...line.options}});}
async function openAddons(line:EntryLine,index:number){addonTarget.value={line,index};await nextTick();addonDialog.value?.showModal();}
function onAddonDialogClick(event:MouseEvent){if(event.target===addonDialog.value)addonDialog.value?.close();}
function setAddon(line:EntryLine,key:string,value:string){if(!value||value==='no'||value==='none')delete line.options[key];else line.options[key]=value;}
function addonSelected(line:EntryLine,key:string){return Boolean(line.options[key]&&!['no','none'].includes(line.options[key]));}
function addonLocked(line:EntryLine,key:string){return isTrackAddon(key)&&trackAddonsLocked(line.options);}
function addonChips(line:EntryLine){return availableAddons(line).flatMap(a=>{const value=line.options[a.key];if(!value||['no','none'].includes(value))return[];const label=locale.value==='zh'?a.label_zh:a.label_en;if(value==='yes')return[label];const choice=a.choices.find(c=>c.value===value);return[choice?(locale.value==='zh'?`${label}：${choice.label_zh}`:`${label}: ${choice.label_en}`):label];});}
async function copyHeader() { await navigator.clipboard?.writeText(headerText.value); }
function clearPreview() { previews.value = []; readyOrders.value = []; preparedPayloads.value = []; error.value = ''; notice.value = ''; }
function linePayload(line: EntryLine) {
  return { window_name: line.window_name.trim(), product_id: Number(line.product_id), width_mm: Number(line.width_mm), height_mm: Number(line.height_mm), quantity: Number(line.quantity), panel_count: Number(line.panel_count), options: {...line.options} };
}
function orderPayload(order: OrderDraft) {
  if (!order.customer_id) throw new Error(tx('请选择客户。','Select a customer.'));
  if (!order.project_name.trim()) throw new Error(tx('请填写项目名称。','Enter a project name.'));
  if (order.project_name.trim().length > 20) throw new Error(tx('ORDER ID 不能超过 20 个字符。','ORDER ID must be 20 characters or fewer.'));
  if (order.installation_required && !order.site_address.trim()) throw new Error(tx('选择 Installed 后，请填写安装地址。','Enter the installation address for an Installed order.'));
  if (!order.lines.length) throw new Error(tx('订单至少需要一行产品。','Each order needs at least one product line.'));
  const lines = order.lines.map(linePayload);
  if (lines.some(line => !line.window_name || !line.product_id || !(line.width_mm > 0) || !(line.height_mm > 0) || !(line.quantity > 0) || !(line.panel_count > 0))) throw new Error(tx('请完整填写每行的窗位、系列、尺寸、数量和扇数。','Complete the window, series, dimensions, quantity and panel count on every line.'));
  for (const line of order.lines) {
    const fields=[...schemaFields(line.product_id).map(f=>f.key),'opening_style','layout_code','vt_post','ht_post','midrail','frame','louver_size','colour','control_rod','fitting'];
    const missing=fields.find(key=>isRequired(line,key)&&!String(key==='panel_count'?line.panel_count:line.options[key]||'').trim());
    if(missing) throw new Error(tx(`“${line.window_name}”还需要填写 ${missing.replaceAll('_',' ')}。`,`“${line.window_name}” still needs ${missing.replaceAll('_',' ')}.`));
  }
  return { customer_id: Number(order.customer_id), project_name: order.project_name.trim(), end_customer_name: (order.end_customer_name || '').trim(), site_address: order.site_address.trim(), installation_required: order.installation_required, lines, submit: order.submit, ...(order.historical_confirmed_deposit_date ? { historical_confirmed_deposit_date: order.historical_confirmed_deposit_date } : {}), submission_key: crypto.randomUUID() };
}
function parseBulk(): OrderDraft[] {
  const rows = pasted.value.trim().split(/\r?\n/).filter(Boolean).map(row => row.split('\t'));
  if (rows.length < 2) throw new Error(tx('请先复制表头和至少一行订单数据。','Paste the header and at least one order row.'));
  const headers = rows[0].map(h => h.trim().toLowerCase());
  const required = bulkHeaders.filter(h => h !== 'End Customer Name (optional)').map(h => h.toLowerCase());
  if (required.some(h => !headers.includes(h))) throw new Error(tx(`表头不匹配。请使用页面提供的模板列。缺少：${required.filter(h => !headers.includes(h)).join('、')}`, `The header does not match the template. Missing: ${required.filter(h => !headers.includes(h)).join(', ')}`));
  const ix = Object.fromEntries(required.map(h => [h, headers.indexOf(h)])) as Record<string,number>;
  const groups = new Map<string, OrderDraft>();
  const customerByCode = new Map(customers.value.flatMap(c => c.customer_code ? [[c.customer_code.toLowerCase(),c] as const] : []));
  const productByCode = new Map(products.value.map(p => [p.source_code.toLowerCase(),p] as const));
  const productByName = new Map(products.value.flatMap(p => [[(p.name_en || '').toLowerCase(),p] as const,[(p.name_zh || '').toLowerCase(),p] as const]));
  rows.slice(1).forEach((cells, index) => {
    const cell = (name: string) => (cells[ix[name]] || '').trim();
    const rowNo = index + 2;
    const ref = cell('order ref'); const code = cell('customer code'); const series = cell('series');
    if (!ref || !code || !cell('project name') || !cell('window name') || !series) throw new Error(tx(`第 ${rowNo} 行缺少订单编号、客户代码、项目名、窗位名称或系列。`,`Row ${rowNo} is missing order ref, customer code, project, window name or series.`));
    const customer = customerByCode.get(code.toLowerCase());
    if (!customer) throw new Error(tx(`第 ${rowNo} 行客户代码“${code}”未匹配到系统客户。`,`Row ${rowNo}: customer code “${code}” was not found.`));
    const product = productByCode.get(series.toLowerCase()) || productByName.get(series.toLowerCase());
    if (!product?.orderable) throw new Error(tx(`第 ${rowNo} 行系列“${series}”没有可用的已确认价格。`,`Row ${rowNo}: series “${series}” has no confirmed order price.`));
    const key = ref.toLowerCase();
    let order = groups.get(key);
    const project = cell('project name'); const address = cell('site address'); const install = ['yes','true','1','是'].includes(cell('installation required').toLowerCase());
    const endCustomer = cell('end customer name (optional)');
    if (!order) { order = { ref, customer_id: customer.customer_id, project_name: project, end_customer_name: endCustomer, site_address: address, installation_required: install, lines: [], submit: false }; groups.set(key,order); }
    if (order.customer_id !== customer.customer_id || order.project_name !== project || order.end_customer_name !== endCustomer || order.site_address !== address || order.installation_required !== install) throw new Error(tx('同一订单的客户和订单信息必须一致。','Rows with the same Order Ref must have matching customer and order details.'));
    let options: unknown;
    try { options = JSON.parse(cell('options json') || '{}'); if(!options||Array.isArray(options)||typeof options!=='object')throw new Error(); } catch { throw new Error(tx(`第 ${rowNo} 行 Options JSON 无效。`,`Row ${rowNo} has invalid Options JSON.`)); }
    const quoteDate = historicalImport.value ? cell('quote date (yyyy-mm-dd)') : '';
    if (historicalImport.value && !/^\d{4}-\d{2}-\d{2}$/.test(quoteDate)) throw new Error(tx(`第 ${rowNo} 行需要填写报价日期（YYYY-MM-DD）。`,`Row ${rowNo} needs a quote date in YYYY-MM-DD format.`));
    if (historicalImport.value && order.historical_confirmed_deposit_date && order.historical_confirmed_deposit_date !== quoteDate) throw new Error(tx(`订单“${ref}”的多行报价日期不一致。`,`Quote dates differ across rows for order “${ref}”.`));
    if (historicalImport.value) order.historical_confirmed_deposit_date = quoteDate;
    order.lines.push({ window_name: cell('window name'), product_id: product.id, width_mm: cell('width (mm)'), height_mm: cell('height (mm)'), quantity: Number(cell('quantity') || 1), panel_count: Number(cell('panels') || 1), options: options as Record<string,string> });
  });
  return [...groups.values()].map(order => ({ ...order, submit: false }));
}
async function preview() {
  clearPreview(); busy.value = true;
  try {
    const orders = mode.value === 'single' ? [orderPayload(draft)] : parseBulk().map(orderPayload);
    const result = await request<Preview[]>('operations/orders/staff/preview',{ orders });
    readyOrders.value = mode.value === 'single' ? [draft] : parseBulk();
    preparedPayloads.value = orders;
    previews.value = result;
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
async function createOrders() {
  if (!previews.value.length || readyOrders.value.length !== previews.value.length) return;
  busy.value = true; error.value = ''; notice.value = '';
  try {
    const orders = preparedPayloads.value.map((order,index) => ({ ...order, submit: readyOrders.value[index].submit }));
    const created = await request<any[]>('operations/orders/staff',{ orders });
    notice.value = tx(`已创建 ${created.length} 个订单。`,`Created ${created.length} order(s).`);
    clearPreview(); pasted.value = '';
    draft.project_name = ''; draft.end_customer_name = ''; draft.site_address = ''; draft.customer_id = ''; draft.lines = [newLine()];
    emit('created');
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
}
onMounted(async () => {
  busy.value = true;
  try {
    const [customerRows,catalog] = await Promise.all([request<Customer[]>('operations/customers'),request<{products:Product[];addons?:Addon[]}>('operations/order-catalog')]);
    customers.value = customerRows; products.value = catalog.products; addons.value = catalog.addons||[];
    draft.lines.push(newLine());
  } catch (cause) { error.value = cause instanceof Error ? cause.message : String(cause); }
  finally { busy.value = false; }
});
</script>

<template>
  <section class="staff-order-entry card">
    <header class="entry-heading"><div><h2>{{ tx('新增订单','New order') }}</h2><p>{{ tx('选择客户，按客户订单的相同价格规则录入产品；金额由系统计算。','Choose a customer and enter products using the customer order pricing rules. Prices are calculated by the system.') }}</p></div><div class="entry-modes"><button type="button" :aria-pressed="mode==='single'" @click="mode='single';clearPreview()">{{ tx('单个订单','Single order') }}</button><button type="button" :aria-pressed="mode==='bulk'" @click="mode='bulk';clearPreview()">{{ tx('粘贴 Excel','Paste from Excel') }}</button></div></header>
    <p v-if="error" class="entry-alert" role="alert">{{ error }}</p><p v-if="notice" class="entry-success" role="status">{{ notice }}</p>
    <template v-if="mode==='single'">
      <div class="entry-fields">
        <label>{{ tx('客户','Customer') }}<select v-model.number="draft.customer_id"><option value="">{{ tx('选择客户','Select customer') }}</option><option v-for="c in customers" :key="c.customer_id" :value="c.customer_id">{{ customerLabel(c) }}</option></select></label>
        <label>{{ tx('ORDER ID','ORDER ID') }}<input v-model="draft.project_name" maxlength="20" :placeholder="tx('最多 20 个字符','Up to 20 characters')" /></label>
        <label>{{ tx('终端客户姓名（选填）','End customer name (optional)') }}<input v-model="draft.end_customer_name" maxlength="200" /></label>
        <label>{{ tx('安装地址','Installation address') }}<input v-model="draft.site_address" :disabled="!draft.installation_required" :placeholder="draft.installation_required?tx('填写安装地址','Enter installation address'):tx('仅安装时填写','Required for installed orders')" /></label>
        <fieldset class="entry-install"><legend>{{ tx('订单类型','Order type') }}</legend><label><input v-model="draft.installation_required" :value="false" type="radio" />{{ tx('Supply Only','Supply Only') }}</label><label><input v-model="draft.installation_required" :value="true" type="radio" />{{ tx('Installed','Installed') }}</label></fieldset>
      </div>
      <div class="entry-lines"><table><thead><tr>
        <th class="entry-row-num">#</th><th>{{ tx('窗户位置 / 名称','Window Location / Name') }}</th><th>{{ tx('宽 (mm)','Width (mm)') }}</th><th>{{ tx('DROP (mm)','DROP (mm)') }}</th><th>{{ tx('材料 / 系列','Material / Series') }}</th><th>{{ tx('开合方式','Opening Style') }}</th><th>{{ tx('扇数','Panels') }}</th><th>{{ tx('布局代码','Layout Code') }}</th><th>{{ tx('竖柱','VT Post') }}</th><th>{{ tx('横柱','HT Post') }}</th><th>{{ tx('中横档','Midrail') }}</th><th>{{ tx('框型','Frame') }}</th><th>{{ tx('叶片尺寸','Louver Size') }}</th><th>{{ tx('颜色','Colour') }}</th><th>{{ tx('控制杆','Control Rod') }}</th><th>{{ tx('安装尺寸','Fitting') }}</th><th>{{ tx('附加项 / 特殊要求','Add-ons / Special Request') }}</th><th>{{ tx('操作','Actions') }}</th>
      </tr></thead><tbody>
        <tr v-for="(line,i) in draft.lines" :key="i">
          <td class="entry-row-num">{{ i+1 }}</td>
          <td><input v-model="line.window_name" :class="{'entry-required':isRequired(line,'window_name')}" /></td>
          <td><input v-model="line.width_mm" type="number" min="1" :class="{'entry-required':isRequired(line,'width_mm')}" /></td>
          <td><input v-model="line.height_mm" type="number" min="1" :class="{'entry-required':isRequired(line,'height_mm')}" /></td>
          <td><select v-model.number="line.product_id" :class="{'entry-required':isRequired(line,'product_id')}" @change="onProductChange(line)"><option value="">{{ tx('选择系列','Select') }}</option><option v-for="p in products.filter(p=>p.orderable)" :key="p.id" :value="p.id">{{ productLabel(p) }}</option></select></td>
          <td><select v-if="choicesFor(line,'opening_style').length" v-model="line.options.opening_style" :class="{'entry-required':isRequired(line,'opening_style')}" @change="onOpeningStyleChange(line)"><option value="">—</option><option v-for="v in choicesFor(line,'opening_style')" :key="v" :value="v">{{ v }}</option></select><input v-else v-model="line.options.opening_style" :class="{'entry-required':isRequired(line,'opening_style')}" @change="onOpeningStyleChange(line)" /></td>
          <td><input v-model.number="line.panel_count" type="number" min="1" :class="{'entry-required':isRequired(line,'panel_count')}" /></td>
          <td><input v-model="line.options.layout_code" :class="{'entry-required':isRequired(line,'layout_code')}" /></td>
          <td><input v-model="line.options.vt_post" :class="{'entry-required':isRequired(line,'vt_post')}" /></td>
          <td><input v-model="line.options.ht_post" /></td>
          <td><input v-model="line.options.midrail" :class="{'entry-required':isRequired(line,'midrail')}" /></td>
          <td><select v-if="isTrackFrameStyle(line)" v-model="line.options.frame" class="entry-required"><option value="Track System">Track System</option></select><select v-else-if="choicesFor(line,'frame').length" v-model="line.options.frame" :class="{'entry-required':isRequired(line,'frame')}"><option value="">—</option><option v-for="v in choicesFor(line,'frame')" :key="v" :value="v">{{ v }}</option></select><input v-else v-model="line.options.frame" :class="{'entry-required':isRequired(line,'frame')}" /></td>
          <td><select v-model="line.options.louver_size" :class="{'entry-required':isRequired(line,'louver_size')}"><option value="">—</option><option v-for="v in choicesFor(line,'louver_size')" :key="v" :value="v">{{ v }}</option></select></td>
          <td><select v-model="line.options.colour" :class="{'entry-required':isRequired(line,'colour')}"><option value="">—</option><option v-for="v in choicesFor(line,'colour')" :key="v" :value="v">{{ v }}</option></select></td>
          <td><select v-if="choicesFor(line,'control_rod').length" v-model="line.options.control_rod" :class="{'entry-required':isRequired(line,'control_rod')}"><option value="">—</option><option v-for="v in choicesFor(line,'control_rod')" :key="v" :value="v">{{ v }}</option></select><input v-else v-model="line.options.control_rod" :class="{'entry-required':isRequired(line,'control_rod')}" /></td>
          <td><select v-model="line.options.fitting" :class="{'entry-required':isRequired(line,'fitting')}"><option value="">—</option><option v-for="v in choicesFor(line,'fitting')" :key="v" :value="v">{{ v }}</option></select></td>
          <td class="entry-addons"><input v-model="line.options.special_request" class="entry-special" :placeholder="tx('特殊要求 / 定制备注','Special request / notes')"/><button type="button" class="entry-addon-trigger" @click="openAddons(line,i)"><SlidersHorizontal :size="14"/>{{ addonChips(line).length?tx(`附加项 · ${addonChips(line).length}`,`Add-ons · ${addonChips(line).length}`):tx('选择附加项','Choose add-ons') }}</button><span v-for="chip in addonChips(line)" :key="chip" class="entry-addon-chip">{{ chip }}</span></td>
          <td class="entry-row-actions"><button type="button" :aria-label="tx('复制行','Copy row')" @click="copyLine(line);clearPreview()"><Copy :size="14"/></button><button type="button" :disabled="draft.lines.length<2" :aria-label="tx('删除行','Delete row')" @click="draft.lines.splice(i,1);clearPreview()"><Trash2 :size="15"/></button></td>
        </tr>
        <tr class="entry-add-row"><td class="entry-row-num"><button type="button" class="entry-add-button" :aria-label="tx('添加一行','Add a row')" @click="addLine();clearPreview()"><Plus :size="17"/></button></td><td colspan="17"></td></tr>
      </tbody></table></div>
      <dialog ref="addonDialog" class="entry-addon-dialog" :aria-label="tx('附加项','Add-ons')" @close="addonTarget=null" @click="onAddonDialogClick"><form v-if="addonTarget" method="dialog"><header><strong>{{ tx('附加项','Add-ons') }} · {{ tx(`第 ${addonTarget.index+1} 行`,`Row ${addonTarget.index+1}`) }}</strong></header><label v-for="a in availableAddons(addonTarget.line)" :key="a.key"><span>{{ locale==='zh'?a.label_zh:a.label_en }}<small v-if="addonLocked(addonTarget.line,a.key)">{{ tx('由开合方式自动决定','Set by Opening Style') }}</small></span><select v-if="a.key==='extra_installation'" :value="addonTarget.line.options[a.key]||'none'" @change="setAddon(addonTarget.line,a.key,($event.target as HTMLSelectElement).value)"><option v-for="c in a.choices" :key="c.value" :value="c.value">{{ locale==='zh'?c.label_zh:c.label_en }}</option></select><input v-else type="checkbox" :checked="addonSelected(addonTarget.line,a.key)" :disabled="addonLocked(addonTarget.line,a.key)" @change="setAddon(addonTarget.line,a.key,($event.target as HTMLInputElement).checked?'yes':'no')"/></label><footer><button type="submit">{{ tx('完成','Done') }}</button></footer></form></dialog>
      <label class="entry-submit"><input v-model="draft.submit" type="checkbox" />{{ tx('创建后提交审核（不勾选则保存为草稿）','Submit for review after creation (otherwise save as draft)') }}</label>
    </template>
    <template v-else>
      <div class="entry-template"><strong>{{ tx('固定列顺序（第一行为表头）','Required column order (first row is the header)') }}</strong><code>{{ headerText }}</code><button class="entry-secondary" type="button" @click="copyHeader">{{ tx('复制表头','Copy header') }}</button><p>{{ tx('每个订单可占多行产品；Order Ref 相同的行会合并为一个订单。Customer Code 使用系统客户代码。Options JSON 可留空 {}。不需要粘贴价格。','Use multiple product rows per order. Rows with the same Order Ref become one order. Customer Code must match the system. Options JSON can be {}. Do not include prices.') }}</p></div>
      <label class="entry-submit"><input v-model="historicalImport" type="checkbox" @change="clearPreview()" />{{ tx('历史订单导入：把报价日期记作创建、确认和定金到账日期（会计入订单、现金流及返利统计）','Historical import: use quote date as creation, acceptance and deposit receipt date (affects order, cash flow and rebate reporting)') }}</label>
      <textarea v-model="pasted" class="entry-paste" spellcheck="false" :placeholder="headerText" @input="clearPreview()"></textarea>
    </template>
    <div class="entry-actions"><button type="button" :disabled="busy || !customers.length || !products.length" @click="preview">{{ busy ? tx('处理中…','Working…') : tx('预览匹配与系统价格','Preview matches and system prices') }}</button><button v-if="previews.length" type="button" :disabled="busy" @click="createOrders">{{ tx(`确认创建 ${previews.length} 个订单`,`Create ${previews.length} order(s)`) }}</button></div>
    <div v-if="previews.length" class="entry-preview"><h3>{{ tx('创建预览','Creation preview') }}</h3><div v-for="(preview,i) in previews" :key="`${preview.customer_id}-${preview.project_name}-${i}`" class="entry-preview-row"><strong>{{ preview.project_name }}</strong><span>{{ customers.find(c=>c.customer_id===preview.customer_id)?.company }} · {{ preview.line_count }} {{ tx('行','lines') }}</span><span>{{ preview.currency || 'NZD' }} {{ preview.total }} <small>({{ tx('定金','deposit') }} {{ preview.deposit }})</small></span></div></div>
  </section>
</template>

<style scoped>
.staff-order-entry{max-width:none;padding:16px;display:grid;gap:12px}.entry-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.entry-heading h2{font-size:18px;margin:0}.entry-heading p{margin:3px 0;color:#52635a}.entry-modes,.entry-actions{display:flex;gap:8px;flex-wrap:wrap}.entry-modes button,.entry-secondary{background:#fff;color:#315844;border:1px solid #dce5df}.entry-modes button[aria-pressed=true]{background:#203d35;color:#fff}.entry-fields{display:grid;grid-template-columns:minmax(170px,1fr) minmax(160px,.9fr) minmax(180px,1fr) minmax(220px,1.3fr) 132px;gap:10px;align-items:end}.entry-fields>label{display:grid;gap:5px;margin:0;font-size:12px;font-weight:650}.entry-fields>label input,.entry-fields>label select{box-sizing:border-box;width:100%;height:40px;min-height:40px;margin:0;padding:7px 9px;border:1px solid #cbd8ce;border-radius:4px;background:#fff;font:inherit;font-weight:400}.entry-fields>label input:disabled{background:#f3f5f3;color:#7d8982}.entry-install{height:40px;box-sizing:border-box;margin:0;padding:3px 7px;display:grid;grid-template-columns:1fr;grid-template-rows:1fr 1fr;gap:1px;border:1px solid #cbd8ce;border-radius:4px}.entry-install legend{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}.entry-install label{display:flex;align-items:center;gap:5px;margin:0;font-size:11px;line-height:1;font-weight:650;white-space:nowrap}.entry-install input,.entry-submit input{width:14px;height:14px;min-height:14px;margin:0}.entry-lines{max-width:100%;overflow:auto;border:1px solid #dce5df;border-radius:5px;background:#fff}.entry-lines table{min-width:2110px;width:100%;border-collapse:separate;border-spacing:0;font-size:12px}.entry-lines th{position:sticky;top:0;z-index:1;background:#edf2ee;color:#30463a;font-size:11px;white-space:nowrap}.entry-lines th,.entry-lines td{padding:6px 5px;border-right:1px solid #e8ede9;border-bottom:1px solid #e4eae5;text-align:left;vertical-align:top}.entry-lines input,.entry-lines select{box-sizing:border-box;width:88px;min-width:72px;height:34px;min-height:34px;margin:0;padding:5px 6px;border:1px solid #d0dad2;border-radius:4px;background:#fff;font:inherit}.entry-lines th:nth-child(2),.entry-lines td:nth-child(2){min-width:145px}.entry-lines td:nth-child(2) input{width:140px}.entry-lines th:nth-child(5),.entry-lines td:nth-child(5){min-width:205px}.entry-lines td:nth-child(5) select{width:200px}.entry-lines th:nth-child(17),.entry-lines td:nth-child(17){min-width:205px}.entry-lines td:nth-child(17) .entry-special{width:200px;margin-bottom:4px}.entry-row-num{position:sticky;left:0;z-index:2;width:34px;min-width:34px!important;background:#f5f7f5;text-align:center!important;vertical-align:middle!important}.entry-lines td.entry-row-num{z-index:2}.entry-required{background:#e8eef0!important;border-color:#8a9ca5!important;box-shadow:inset 0 0 0 1px rgba(53,69,82,.08)}.entry-required:focus{outline:2px solid #354552;outline-offset:1px}.entry-add-row td{height:35px;padding:3px 5px!important}.entry-add-row td:not(.entry-row-num){background:#fff}.entry-add-button{display:grid;place-items:center;width:27px;height:27px;min-height:27px;padding:0;border:1px solid #435a67;border-radius:50%;background:#354552;color:white;cursor:pointer}.entry-add-button:hover{background:#293b46}.entry-addons{min-width:210px}.entry-addon-trigger{display:inline-flex;align-items:center;gap:5px;min-height:30px;padding:0 8px;border:1px dashed #a9b8ad;border-radius:4px;background:#fff;color:#29493d;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap}.entry-addon-chip{display:inline-block;margin:4px 4px 0 0;padding:2px 6px;border-radius:999px;background:#e7f0eb;color:#29493d;font-size:10px}.entry-row-actions button{display:grid;place-items:center;width:30px;height:30px;min-height:30px;padding:0;border:1px solid #dce5df;border-radius:4px;background:white;color:#8a3b2c;cursor:pointer}.entry-row-actions button:disabled{opacity:.4;cursor:not-allowed}.entry-addon-dialog{width:min(440px,calc(100vw - 32px));padding:0;border:0;border-radius:8px;box-shadow:0 18px 50px rgba(20,35,30,.25)}.entry-addon-dialog::backdrop{background:rgba(20,30,26,.35)}.entry-addon-dialog form{padding:18px 20px}.entry-addon-dialog header{margin-bottom:12px}.entry-addon-dialog label{display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center;padding:8px 0;border-bottom:1px solid #edf1ee;font-size:13px}.entry-addon-dialog label span{display:grid;gap:2px}.entry-addon-dialog small{color:#62716b;font-size:11px}.entry-addon-dialog select{height:34px;padding:4px 7px;border:1px solid #ccd7cf;border-radius:4px;background:white}.entry-addon-dialog input[type=checkbox]{width:18px;height:18px;accent-color:#354552}.entry-addon-dialog footer{display:flex;justify-content:flex-end;margin-top:14px}.entry-addon-dialog footer button{min-height:34px;padding:0 15px;background:#354552;color:white;border:0;border-radius:5px}.entry-submit{display:flex;align-items:center;gap:8px;margin:0!important}.entry-template{display:grid;gap:6px}.entry-template code{display:block;overflow:auto;padding:8px;background:#f5f8f5;border:1px solid #dce5df;border-radius:5px;white-space:nowrap}.entry-template p{margin:0;color:#52635a}.entry-paste{width:100%;min-height:220px;resize:vertical;font:12px/1.5 ui-monospace,Consolas,monospace;padding:10px;border:1px solid #cdd9d1;border-radius:6px}.entry-actions{justify-content:flex-end}.entry-preview{border-top:1px solid #dce5df;padding-top:8px}.entry-preview h3{margin:0 0 6px}.entry-preview-row{display:grid;grid-template-columns:minmax(160px,1fr) minmax(140px,1fr) auto;gap:12px;padding:6px 0;border-bottom:1px solid #edf1ee}.entry-preview-row small{color:#52635a}.entry-alert,.entry-success{padding:8px 10px;border-radius:5px;margin:0}.entry-alert{background:#fae8e1;color:#842b16}.entry-success{background:#e5efdd;color:#17523a}
@media(max-width:1000px){.entry-fields{grid-template-columns:repeat(2,minmax(0,1fr))}.entry-preview-row{grid-template-columns:1fr}}
@media(max-width:560px){.entry-heading{align-items:flex-start;flex-direction:column}.entry-fields{grid-template-columns:1fr}.staff-order-entry{padding:12px}}
</style>
