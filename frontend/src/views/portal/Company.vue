<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { portalRequest } from "../../portal-api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const profile = ref<any>(null);
const draft = ref<any>({});
const loading = ref(true);
const editing = ref(false);
const saving = ref(false);
const error = ref("");
const notice = ref("");
const productInterests = computed(() => (profile.value?.product_interests || []).map((item: any) => `${item.name} · ${item.monthly_sqm} m²/month`).join("; "));

function beginEdit() {
  error.value = "";
  notice.value = "";
  draft.value = {
    company: profile.value.company || "",
    contact_name: profile.value.contact_name || "",
    email: profile.value.email || "",
    phone: profile.value.phone || "",
    company_address: profile.value.company_address || "",
    nzbn: profile.value.nzbn || "",
    finance_email: profile.value.finance_email || "",
    finance_phone: profile.value.finance_phone || "",
    application_notes: profile.value.application_notes || "",
    product_interests: (profile.value.product_interests || []).map((item: any) => ({ ...item, monthly_sqm: String(item.monthly_sqm || "") })),
  };
  editing.value = true;
}

async function save() {
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    profile.value = await portalRequest<any>("me", {
      company: draft.value.company.trim(),
      contact_name: draft.value.contact_name.trim(),
      email: draft.value.email.trim(),
      phone: draft.value.phone.trim(),
      company_address: draft.value.company_address.trim(),
      nzbn: draft.value.nzbn.trim() || null,
      finance_email: draft.value.finance_email.trim() || null,
      finance_phone: draft.value.finance_phone.trim() || null,
      application_notes: draft.value.application_notes.trim(),
      product_interests: draft.value.product_interests.map((item: any) => ({ product_id: item.product_id, monthly_sqm: item.monthly_sqm })),
    });
    editing.value = false;
    notice.value = tx("资料已保存。若修改了主要联系人邮箱，新的邮箱也会作为登录名。", "Profile saved. If you changed the primary contact email, it is now your sign-in name too.");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  try {
    profile.value = await portalRequest<any>("me");
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="company-page">
    <header class="profile-heading"><h1>{{ tx("个人资料", "My Profile") }}</h1><button v-if="profile && !editing" type="button" @click="beginEdit">{{ tx("编辑资料", "Edit profile") }}</button></header>
    <div v-if="loading" class="loading">{{ tx("加载中...", "Loading...") }}</div>
    <div v-else-if="profile" class="company-card">
      <form v-if="editing" class="profile-form" @submit.prevent="save">
        <label>{{ tx("公司全名", "Company name") }}<input v-model="draft.company" required minlength="2" maxlength="200" /></label>
        <label>{{ tx("主要联系人", "Primary contact") }}<input v-model="draft.contact_name" required minlength="2" maxlength="200" /></label>
        <label>{{ tx("主要联系人邮箱 / 登录名", "Primary contact email / sign-in") }}<input v-model="draft.email" type="email" required maxlength="200" /></label>
        <label>{{ tx("主要联系人电话", "Primary contact phone") }}<input v-model="draft.phone" required minlength="5" maxlength="100" /></label>
        <label>{{ tx("公司地址", "Company address") }}<textarea v-model="draft.company_address" required minlength="5" maxlength="1000" rows="2" /></label>
        <label>NZBN<input v-model="draft.nzbn" inputmode="numeric" maxlength="13" pattern="[0-9]{13}" /></label>
        <label>{{ tx("财务负责人邮箱", "Finance contact email") }}<input v-model="draft.finance_email" type="email" maxlength="200" /></label>
        <label>{{ tx("财务负责人电话", "Finance contact phone") }}<input v-model="draft.finance_phone" maxlength="100" /></label>
        <label class="profile-wide">{{ tx("补充信息", "Additional information") }}<textarea v-model="draft.application_notes" maxlength="2000" rows="2" /></label>
        <fieldset v-if="draft.product_interests.length" class="interest-list profile-wide"><legend>{{ tx("意向产品和每月预计采购面积", "Product interests and estimated monthly area") }}</legend>
          <label v-for="item in draft.product_interests" :key="item.product_id" class="interest-row"><span>{{ item.name }}</span><span class="sqm-input"><input v-model="item.monthly_sqm" type="number" min="0.01" max="100000" step="0.01" required /><small>m² / month</small></span></label>
        </fieldset>
        <p v-if="error" class="profile-message error" role="alert">{{ error }}</p>
        <div class="profile-actions profile-wide"><button type="submit" :disabled="saving">{{ saving ? tx("保存中…", "Saving…") : tx("保存资料", "Save profile") }}</button><button type="button" class="secondary" :disabled="saving" @click="editing=false">{{ tx("取消", "Cancel") }}</button></div>
      </form>
      <div v-else class="info-section">
        <h2>{{ profile.company }}</h2>
        <dl>
          <dt>{{ tx("联系人", "Contact Name") }}</dt><dd>{{ profile.contact_name }}</dd>
          <dt>{{ tx("邮箱 / 登录名", "Email / sign-in") }}</dt><dd>{{ profile.email }}</dd>
          <dt>{{ tx("电话", "Phone") }}</dt><dd>{{ profile.phone }}</dd>
          <dt>{{ tx("公司地址", "Company Address") }}</dt><dd>{{ profile.company_address }}</dd>
          <dt>NZBN</dt><dd>{{ profile.nzbn || "—" }}</dd>
          <dt>{{ tx("财务邮箱", "Finance Email") }}</dt><dd>{{ profile.finance_email || "—" }}</dd>
          <dt>{{ tx("财务电话", "Finance Phone") }}</dt><dd>{{ profile.finance_phone || "—" }}</dd>
          <template v-if="profile.product_interests?.length"><dt>{{ tx("意向产品", "Interested Products") }}</dt><dd>{{ productInterests }}</dd></template>
          <template v-if="profile.application_notes"><dt>{{ tx("补充信息", "Additional Information") }}</dt><dd>{{ profile.application_notes }}</dd></template>
        </dl>
      </div>
      <p v-if="notice" class="profile-message success" role="status">{{ notice }}</p>
    </div>
    <div v-else class="empty">{{ tx("无法加载公司资料", "Unable to load company profile") }}<p v-if="error" class="profile-message error">{{ error }}</p></div>
  </div>
</template>

<style scoped>
.company-page{max-width:900px}.profile-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:20px}.company-page h1{font-family:var(--font-display);font-size:32px;font-weight:600;margin:0}.loading,.empty{text-align:center;padding:60px 20px;font-size:16px;color:rgba(27,36,33,.6)}.company-card{padding:28px;background:#fff;border:1px solid var(--line);border-radius:10px}.info-section h2{font-family:var(--font-display);font-size:26px;font-weight:600;margin:0 0 20px;color:var(--cord)}.info-section dl{display:grid;grid-template-columns:190px 1fr;gap:13px 20px;margin:0}.info-section dt{font-weight:600;font-size:13px;color:rgba(27,36,33,.65)}.info-section dd{margin:0;font-size:14px;color:var(--ink);overflow-wrap:anywhere}.profile-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.profile-form label{display:grid;gap:5px;font-size:13px;font-weight:600}.profile-form input,.profile-form textarea{width:100%;min-height:40px;border:1px solid var(--line);border-radius:7px;padding:9px 11px;font:inherit;font-weight:400;color:var(--ink)}.profile-wide{grid-column:1/-1}.interest-list{border:1px solid var(--line);border-radius:8px;padding:12px}.interest-list legend{padding:0 6px;font-weight:650;font-size:13px}.interest-row{display:flex!important;align-items:center;justify-content:space-between;gap:15px;padding:8px 0;border-bottom:1px solid #edf0ef}.interest-row:last-child{border:0}.sqm-input{display:flex;align-items:center;gap:7px}.sqm-input input{width:115px}.sqm-input small{white-space:nowrap;color:#66736d}.profile-actions{display:flex;gap:9px}.profile-message{grid-column:1/-1;padding:10px 12px;margin:0;border-radius:7px;font-size:13px}.profile-message.error{background:#fff0ed;color:#8f3425}.profile-message.success{margin-top:16px;background:#edf6ef;color:#21613e}.secondary{background:transparent;color:var(--ink)}@media(max-width:700px){.company-card{padding:18px}.company-page h1{font-size:25px}.profile-form{grid-template-columns:1fr}.profile-form>*{grid-column:1}.info-section dl{grid-template-columns:1fr;gap:6px}.info-section dd{margin-bottom:9px}.profile-actions{flex-wrap:wrap}.profile-actions button{flex:1}}
</style>
