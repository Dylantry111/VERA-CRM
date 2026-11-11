<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { request } from '../crm-api';

const props=defineProps<{locale:string}>();
const tx=(zh:string,en:string)=>props.locale==='zh'?zh:en;
const state=ref<any>(null); const maxLength=ref(20); const busy=ref(false); const error=ref(''); const notice=ref('');
onMounted(async()=>{try{state.value=await request('operations/settings');maxLength.value=state.value?.order_number_max_length??20}catch(e){error.value=e instanceof Error?e.message:String(e)}});
async function save(){busy.value=true;error.value='';notice.value='';try{const result=await request<{max_length:number}>('operations/settings/order-number-limit',{max_length:Number(maxLength.value)});maxLength.value=result.max_length;notice.value=tx('已保存。仅影响之后创建或修改的订单 ID。','Saved. This applies to order IDs created or edited from now on.')}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{busy.value=false}}
</script>
<template>
  <section class="ops-settings"><h2>{{ tx('系统状态','System status') }}</h2><p>{{ tx('账单模板和付款信息已移至 Accounting → Invoice → Invoice settings。','Invoice templates and payment details are managed in Accounting → Invoice → Invoice settings.') }}</p>
    <p v-if="error" class="message error">{{ error }}</p><div v-if="state" class="ops-grid"><article><span>{{ tx('发件','Outgoing mail') }}</span><h3>{{ state.email?.mode==='demo'?(state.email?.configured?tx('演示发件就绪 · 仅自己','Demo mail ready · owner only'):tx('演示发件未就绪','Demo mail not ready')):state.email?.configured?tx('已配置','Configured'):tx('未配置','Not configured') }}</h3><p>{{ state.email?.mode==='demo'?tx('客户不会收到演示邮件。','Customers do not receive demo emails.'):state.email?.sender||tx('没有可显示的发件地址','No sender address to show') }}</p></article><article><span>{{ tx('存储','Storage') }}</span><h3>{{ state.storage||'—' }}</h3></article><article><span>{{ tx('数据库','Database') }}</span><h3>{{ state.database||'—' }}</h3></article></div>
    <form v-if="state" class="limit" @submit.prevent="save"><h3>{{ tx('订单 ID 最大长度','Maximum Order ID length') }}</h3><p>{{ tx('订单 ID 最多可包含的字符数；已有订单号不会被修改。范围：10–20。','Maximum characters for new or manually edited order IDs. Existing IDs are unchanged. Range: 10–20.') }}</p><label>{{ tx('字符数','Characters') }}<input v-model.number="maxLength" type="number" min="10" max="20" required /></label><button :disabled="busy">{{ busy?tx('保存中…','Saving…'):tx('保存限制','Save limit') }}</button><p v-if="notice" class="message success">{{ notice }}</p><p v-if="error" class="message error">{{ error }}</p></form>
  </section>
</template>
<style scoped>
.ops-settings{padding:8px 0 28px}.ops-settings h2{margin:0 0 8px;font-size:20px}.ops-settings>p{max-width:720px;color:#58675f;font-size:13px;line-height:1.55}.ops-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:16px}.ops-grid article,.limit{padding:15px;border:1px solid #dfe7e1;border-radius:8px;background:#fff}.ops-grid span{color:#52635a;font-size:12px}.ops-grid h3{margin:8px 0 0;font-size:16px}.ops-grid p,.limit p{color:#5c6b62;font-size:12px;line-height:1.5}.limit{max-width:640px;margin-top:18px}.limit h3{margin:0}.limit label{display:grid;gap:5px;max-width:240px;font-size:12px;font-weight:650}.limit input{height:36px;padding:5px 8px;border:1px solid #ccd7cf;border-radius:5px}.limit button{margin-top:12px;min-height:38px;padding:0 14px;border:0;border-radius:999px;background:#0f6e5c;color:#fff;font-weight:650}.message{padding:9px 12px;border-radius:6px;font-size:12px}.error{background:#fff0ed;color:#8f3425}.success{background:#edf5ef;color:#17523a}@media(max-width:700px){.ops-grid{grid-template-columns:1fr}}
</style>
