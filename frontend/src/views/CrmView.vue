<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useI18n } from "vue-i18n";
import { request, session } from "../crm-api";
import ProductManager from "../components/ProductManager.vue";
import IntegrationStatus from "../components/IntegrationStatus.vue";
import ProjectDesk from "../components/ProjectDesk.vue";
import PricingKnowledge from "../components/PricingKnowledge.vue";
import SampleDashboard from "../components/SampleDashboard.vue";
import PortalCustomers from "../components/PortalCustomers.vue";
import CrmGuide from "../components/CrmGuide.vue";
import { FolderKanban, Users, BarChart3, Package, Settings, Truck, Wallet, BookOpen } from "lucide-vue-next";
import type { ApiProduct } from "../api";

const { locale } = useI18n();
const tx = (zh: string, en: string) => (locale.value === "zh" ? zh : en);
const signed = ref(!!session.token);
const busy = ref(false);
const error = ref("");
const message = ref("");
const route = useRoute();
const router = useRouter();
const tab = computed(() => String(route.params.section || 'projects'));
const credentials = reactive({ username: "", password: "" });
const products = ref<ApiProduct[]>([]);
const emailMode = ref('demo');
const emailEnabled = ref(false);
const pendingTradeApplications = ref(0);
const me = ref({ username: "", name: "", role: "staff" });
const passwordOpen = ref(false);
const accountMenu = ref<HTMLDetailsElement>();
function closeAccountMenu() { 
  if (accountMenu.value) {
    accountMenu.value.open = false;
    const summary = accountMenu.value.querySelector('summary');
    if (summary && document.activeElement && accountMenu.value.contains(document.activeElement)) {
      summary.focus();
    }
  }
}
function dismissAccountMenu(event: PointerEvent) {
  if (event.target instanceof Node && !accountMenu.value?.contains(event.target)) closeAccountMenu();
}
onMounted(() => document.addEventListener("pointerdown", dismissAccountMenu));
onUnmounted(() => document.removeEventListener("pointerdown", dismissAccountMenu));
const passwordForm = reactive({ current: "", next: "", confirm: "" });
const users = ref<{ username: string; name: string; role: string; active: number }[]>([]);
const newUser = reactive({ username: "", name: "", password: "", role: "staff" });
const nav = computed(() => [
  { key: "dashboard", label: tx("Dashboard", "Dashboard") },
  { key: "projects", label: tx("Orders", "Orders") },
  { key: "shipments", label: tx("Shipment", "Shipment") },
  { key: "customers", label: tx("Customer", "Customer"), badge: pendingTradeApplications.value },
  { key: "providers", label: tx("Supplier", "Supplier") },
  { key: "pricing", label: tx("Price Knowledge", "Price Knowledge") },
  { key: "finance", label: tx("Accounts and Rebates", "Accounts and Rebates") },
  { key: "products", label: tx("Product", "Product") },
  { key: "help", label: tx("Operating Guide", "Operating Guide") },
  { key: "users", label: tx("Settings", "Settings") },
]);
const pageTitle = computed(() => nav.value.find((item) => item.key === tab.value)?.label || tx("系统设置", "Settings"));

async function act(fn: () => Promise<void>) {
  busy.value = true;
  error.value = "";
  message.value = "";
  try {
    await fn();
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : String(cause);
    if (!session.token) signed.value = false;
  } finally {
    busy.value = false;
  }
}

async function load() {
  const [catalogue, who, runtime] = await Promise.all([
    request<ApiProduct[]>("admin/products"),
    request<{ username: string; name: string; role: string }>("auth/me"),
    request<{email_mode:string;email_delivery_enabled:boolean;demo_email_address:string}>('operations/runtime'),
  ]);
  products.value = catalogue;
  me.value = who;
  emailMode.value = runtime.email_mode;
  emailEnabled.value = runtime.email_delivery_enabled;
  if (who.role === "admin") {
    users.value = await request("users");
    await refreshTradeApplicationCount();
  } else pendingTradeApplications.value = 0;
}

async function refreshTradeApplicationCount() {
  if (me.value.role !== "admin") return;
  try { pendingTradeApplications.value = (await request<{ pending: number }>("operations/trade-applications/count")).pending; }
  catch { /* The customer inbox remains available if the count refresh is temporarily unavailable. */ }
}


async function changePassword() {
  if (passwordForm.next !== passwordForm.confirm) {
    error.value = tx("两次新密码不一致", "The new passwords do not match");
    return;
  }
  await act(async () => {
    await request("auth/password", { current: passwordForm.current, new: passwordForm.next });
    session.token = "";
    signed.value = false;
    passwordForm.current = "";
    passwordForm.next = "";
    passwordForm.confirm = "";
    passwordOpen.value = false;
    message.value = tx("密码已更新，请用新密码重新登录", "Password updated. Sign in again with the new password");
  });
}

async function addUser() {
  await act(async () => {
    await request("users", { ...newUser });
    newUser.username = "";
    newUser.name = "";
    newUser.password = "";
    await load();
    message.value = tx("用户已添加", "User added");
  });
}

async function setRole(username: string, role: string) {
  await act(async () => {
    await request(`users/${username}/role`, { role });
    await load();
    message.value = tx("权限已更新", "Access updated");
  });
}

function onRole(username: string, event: Event) {
  void setRole(username, (event.target as HTMLSelectElement).value);
}

async function login() {
  await act(async () => {
    const result = await request<{ token: string }>("auth/login", credentials);
    session.token = result.token;
    signed.value = true;
    credentials.password = "";
    await load();
  });
}

async function logout() {
  await act(async () => {
    await request("auth/logout", {});
    session.token = "";
    signed.value = false;
  });
}

function openTab(key: string) {
  void router.push(`/crm/${key}`);
  window.scrollTo({ top: 0 });
}

onMounted(() => {
  if (signed.value) void act(load);
});
</script>

<template>
  <main class="page crm" :class="{ 'is-signed': signed }">
    <p v-if="error" class="alert" role="alert">{{ error }}</p>
    <p v-if="message" class="success" role="status">{{ message }}</p>

    <form v-if="!signed" class="card login" @submit.prevent="login">
      <h1>{{ tx("内部登录", "Internal sign in") }}</h1>
      <p>{{ tx("客户资料仅对已登录用户开放", "Customer information requires sign in") }}</p>
      <label>{{ tx("用户名", "Username") }}<input v-model="credentials.username" autocomplete="username" required /></label>
      <label>{{ tx("密码", "Password") }}<input v-model="credentials.password" type="password" autocomplete="current-password" required /></label>
      <button :disabled="busy">{{ tx("登录", "Sign in") }}</button>
    </form>

    <template v-else>
      <nav class="top-nav" :aria-label="tx('主导航','Main navigation')">
        <router-link to="/" class="crm-brand" :aria-label="tx('VERA 首页','VERA home')"><img src="/images/vera-logo.png" alt="VERA Shading Solutions" /></router-link>
        <button v-for="item in nav" v-show="item.key !== 'users' || me.role === 'admin'" :key="item.key" type="button" :class="{ current: tab === item.key }" @click="openTab(item.key)">
          <BarChart3 v-if="item.key==='dashboard'" :size="18" aria-hidden="true" />
          <FolderKanban v-else-if="item.key==='projects'" :size="18" aria-hidden="true" />
          <Truck v-else-if="item.key==='shipments' || item.key==='providers'" :size="18" aria-hidden="true" />
          <Users v-else-if="item.key==='customers'" :size="18" aria-hidden="true" />
          <BookOpen v-else-if="item.key==='pricing' || item.key==='help'" :size="18" aria-hidden="true" />
          <Wallet v-else-if="item.key==='finance'" :size="18" aria-hidden="true" />
          <Package v-else-if="item.key==='products'" :size="18" aria-hidden="true" />
          <Settings v-else-if="item.key==='users'" :size="18" aria-hidden="true" />
          <span>{{ item.label }}</span><span v-if="item.key === 'customers' && item.badge" class="nav-badge">{{ item.badge }}</span>
        </button>
        <details ref="accountMenu" class="account-menu">
          <summary :aria-label="tx('账户菜单', 'Account menu')" :title="me.name"><span>{{ (me.name || 'V').slice(0, 1) }}</span></summary>
          <div class="account-dropdown">
            <div class="account-identity"><strong>{{ me.name }}</strong><small>{{ me.role === 'admin' ? tx('管理员', 'Admin') : tx('员工', 'Staff') }}</small></div>
            <button type="button" @click="passwordOpen = !passwordOpen; closeAccountMenu()">{{ tx('修改密码', 'Change password') }}</button>
            <button type="button" @click="logout(); closeAccountMenu()">{{ tx('退出', 'Sign out') }}</button>
          </div>
        </details>
      </nav>
      <header class="crm-bar">
        <nav class="page-context" :aria-label="tx('当前位置', 'Breadcrumb')">
          <span>VERA</span><span aria-hidden="true">/</span><span>CRM</span><span aria-hidden="true">/</span><strong aria-current="page">{{ pageTitle }}</strong>
        </nav>
      </header>
      <form v-if="passwordOpen" class="password-form" @submit.prevent="changePassword">
        <label>{{ tx("当前密码", "Current password") }}<input v-model="passwordForm.current" type="password" autocomplete="current-password" required /></label>
        <label>{{ tx("新密码", "New password") }}<input v-model="passwordForm.next" type="password" autocomplete="new-password" minlength="8" required /></label>
        <label>{{ tx("再输入一次", "Repeat the new password") }}<input v-model="passwordForm.confirm" type="password" autocomplete="new-password" minlength="8" required /></label>
        <button :disabled="busy">{{ tx("保存密码", "Save password") }}</button>
      </form>
      <PricingKnowledge v-if="tab === 'pricing'" :admin="me.role === 'admin'" />
      <ProjectDesk v-if="['projects','shipments','providers','finance'].includes(tab)" :key="tab" :workspace="tab" :email-enabled="emailEnabled" :email-mode="emailMode" :admin="me.role === 'admin'" />
      <CrmGuide v-if="tab==='help'" :demo="emailMode!=='live'" :delivery-enabled="emailEnabled" />
      <PortalCustomers v-if="tab === 'customers'" :admin="me.role === 'admin'" :email-enabled="emailEnabled" :email-mode="emailMode" @applications-updated="refreshTradeApplicationCount" />
      <SampleDashboard v-if="tab === 'dashboard'" />
      <ProductManager v-if="tab === 'products'" :admin="me.role === 'admin'" @updated="act(load)" />
      <div v-if="tab === 'users' && me.role === 'admin'" class="settings-layout">
        <IntegrationStatus :locale="locale" />
        <section class="card">
          <h2>{{ tx("用户与权限", "Users & access") }}</h2>
          <form class="user-form" @submit.prevent="addUser">
            <label>{{ tx("用户名", "Username") }}<input v-model="newUser.username" required pattern="[a-z0-9._-]{2,40}" autocomplete="off" /></label>
            <label>{{ tx("姓名", "Name") }}<input v-model="newUser.name" required autocomplete="off" /></label>
            <label>{{ tx("初始密码", "Starting password") }}<input v-model="newUser.password" type="password" minlength="8" required autocomplete="new-password" /></label>
            <label>{{ tx("权限", "Access") }}
              <select v-model="newUser.role">
                <option value="staff">{{ tx("销售", "Sales") }}</option>
                <option value="admin">{{ tx("管理员", "Admin") }}</option>
              </select>
            </label>
            <button :disabled="busy">{{ tx("添加用户", "Add user") }}</button>
          </form>
          <div class="table-wrap">
            <table>
              <thead><tr><th>{{ tx("用户名", "Username") }}</th><th>{{ tx("姓名", "Name") }}</th><th>{{ tx("权限", "Access") }}</th></tr></thead>
              <tbody>
                <tr v-for="person in users" :key="person.username">
                  <td>{{ person.username }}</td>
                  <td>{{ person.name }}</td>
                  <td>
                    <select :value="person.role" @change="onRole(person.username, $event)">
                      <option value="admin">{{ tx("管理员", "Admin") }}</option>
                      <option value="staff">{{ tx("销售", "Sales") }}</option>
                    </select>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </template>
  </main>
</template>

<style scoped>
.crm {
  --fs-page-title: 20px; --lh-page-title: 1.35;
  --fs-title: 15px; --lh-title: 1.5;
  --fs-heading: 14px; --lh-heading: 1.5;
  --fs-body: 13px; --lh-body: 1.55;
  --fs-meta: 12px; --lh-meta: 1.5;
  --fw-body: 400;
  --fw-emphasis: 600;
  font-family: var(--font-body, "Figtree", "Noto Sans SC", sans-serif); font-size: var(--fs-body); line-height: var(--lh-body); color: #1b2421; background: #f5f6f2; min-height: 100vh; padding: 24px 20px 36px; overflow: visible;
}
.crm.is-signed { padding-left: 252px; }
.crm.is-signed.rail-collapsed { padding-left: 92px; }
.desk-rail.is-collapsed { width: 72px; }
.desk-rail.is-collapsed .rail-label, .desk-rail.is-collapsed .user-meta { display: none; }
.desk-rail.is-collapsed .rail-brand { display: flex; justify-content: center; padding-inline: 0; }
.rail-brand { display: flex; align-items: center; justify-content: space-between; }
.rail-collapse { min-width: 44px; justify-content: center; }
@media(max-width:800px) {
  .crm.is-signed.rail-collapsed { padding: 16px; }
  .desk-rail.is-collapsed { width: auto; }
  .desk-rail.is-collapsed .rail-label { display: initial; }
  .rail-collapse { display: none; }
}
.desk-rail { position: fixed; inset: 0 auto 0 0; width: 228px; background: #1a2823; color: #e7eee9; padding: 24px 12px; display: flex; flex-direction: column; gap: 4px; }
.rail-brand { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); letter-spacing: 0.16em; padding: 4px 12px 16px; }
.crm h1, .crm h2, .crm h3, .crm h4, .crm h5, .crm h6 { font-weight: var(--fw-emphasis); }
.desk-rail button { display: flex; align-items: center; gap: 10px; min-height: 44px; border: 0; background: transparent; color: #e7eee9; padding: 10px 12px; text-align: left; font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-body); border-radius: 6px; transition: background 0.2s; }
.desk-rail button:hover { background: rgba(255,255,255,0.08); }
.desk-rail button:focus-visible { outline: 2px solid #0f6e5c; outline-offset: 2px; }
.desk-rail button.current { background: #0f6e5c; color: white; }
.rail-bottom { margin-top: auto; display: flex; gap: 10px; align-items: center; padding: 16px 12px; border-top: 1px solid rgba(231, 238, 233, 0.16); }
.user-avatar { display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; background: #8e9a94; color: #1a2823; font-size: var(--fs-heading); line-height: 1; }
.user-meta strong { display: block; font-size: var(--fs-heading); line-height: var(--lh-heading); }
.user-meta small { display: block; font-size: var(--fs-meta); line-height: var(--lh-meta); opacity: 0.75; margin-top: 2px; }
.crm-bar { display: flex; align-items: flex-end; gap: 12px; min-height: 72px; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid #e1e6df; }
.page-context { margin-right: auto; }
.page-context span { font-size: var(--fs-meta); line-height: var(--lh-meta); letter-spacing: 0.14em; color: #5d6b64; }
.page-context h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 6px 0 0; }
.crm-bar button, .login button, .password-form button, .user-form button { min-height: 44px; font-size: var(--fs-body); line-height: var(--lh-body); padding: 8px 14px; border-radius: 6px; border: 1px solid #0f6e5c; background: #0f6e5c; color: white; font-weight: var(--fw-body); }
.crm-bar button.secondary { background: white; color: #24342c; border-color: #d5ddd6; }
.card, .login { background: white; border: 1px solid #e1e6df; border-radius: 8px; padding: 24px; }
.login { max-width: 440px; margin: 48px auto; }
.login h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 0 0 8px; }
.login p, .card p { font-size: var(--fs-body); line-height: var(--lh-body); }
.crm label { display: block; margin: 14px 0; font-size: var(--fs-body); line-height: var(--lh-body); }
.crm input, .crm select, .crm button { line-height: var(--lh-body); }
.crm select {
  -webkit-appearance: none;
  appearance: none;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16'%3E%3Cpath fill='%2352615c' d='M4 6l4 4 4-4z'/%3E%3C/svg%3E");
  background-repeat: no-repeat;
  background-position: right 10px center;
  padding-right: 30px;
}
.crm select:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.crm option { line-height: var(--lh-body); }
.crm input, .crm select { width: 100%; box-sizing: border-box; min-height: 44px; margin-top: 6px; padding: 8px 12px; font-size: var(--fs-body); border: 1px solid #d5ddd6; border-radius: 6px; }
.password-form, .user-form { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)) auto; gap: 12px; align-items: end; margin-bottom: 16px; }
.password-form label, .user-form label { margin: 0; }
.settings-layout { display: grid; gap: 24px; }
.card h2 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); margin: 0 0 16px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { text-align: left; font-size: var(--fs-body); line-height: var(--lh-body); padding: 12px 10px; border-bottom: 1px solid #e1e6df; }
th, .crm strong, .crm b { font-weight: var(--fw-emphasis); }
.alert { padding: 12px 16px; background: #fae8e1; color: #842b16; }
.success { padding: 12px 16px; background: #e5efdd; }
@media (max-width: 800px) {
  .crm, .crm.is-signed { padding: 16px; }
  .desk-rail { position: static; width: auto; margin: -16px -16px 20px; display: grid; grid-template-columns: 1fr 1fr; }
  .rail-brand, .rail-bottom { display: none; }
  .password-form, .user-form { grid-template-columns: 1fr; }
  .crm-bar { flex-wrap: wrap; }
  .page-context { flex-basis: 100%; }
}
@media (max-width: 390px) {
  .crm, .crm.is-signed { padding: 12px; }
  .desk-rail { grid-template-columns: 1fr 1fr; gap: 2px; margin: -12px -12px 16px; }
  .crm-bar { min-height: 60px; margin-bottom: 16px; }
  .page-context h1 { font-size: var(--fs-title); line-height: var(--lh-title); }
}

.crm { font-family: Inter, "Segoe UI", "Microsoft YaHei", sans-serif; background: #f3f6f4; }
.crm :deep(*) { box-sizing: border-box; }
.crm :deep(h1), .crm :deep(h2), .crm :deep(h3), .crm :deep(h4) { font-family: inherit; letter-spacing: -.015em; }
.crm :deep(button), .crm :deep(input), .crm :deep(select), .crm :deep(textarea) { font-family: inherit; }
.crm-bar { min-height: 64px; align-items: center; margin-bottom: 24px; }
.page-context h1 { font-size: var(--fs-page-title); line-height: var(--lh-page-title); font-weight: var(--fw-emphasis); }
.desk-rail { width: 220px; padding: 28px 14px; background: #19392d; box-sizing: border-box; }
.crm.is-signed { padding-left: 248px; }
.desk-rail button { font-size: var(--fs-heading); line-height: var(--lh-heading); padding: 10px 12px; border-radius: 8px; }
.desk-rail button.current { background: #315844; }
.crm-bar button.secondary { font-size: var(--fs-body); line-height: var(--lh-body); min-height: 44px; padding: 8px 12px; font-weight: var(--fw-body); }
@media(max-width:800px) { .crm.is-signed { padding: 16px; } .desk-rail { width: auto; padding: 12px; gap: 4px; } .crm-bar { gap: 8px; } }
@media(max-width:390px) { .crm.is-signed { padding: 12px; } .desk-rail button { font-size: var(--fs-meta); line-height: var(--lh-meta); min-height: 44px; font-weight: var(--fw-body); } }
.desk-rail>button{justify-content:flex-start;text-align:left}
.desk-rail>button>svg{flex:0 0 20px;width:20px;height:20px}
.demo-notice{padding:8px 12px;margin:0 0 12px;border:1px solid #c6dace;background:#edf5ef;color:#244f37;border-radius:6px;font-size:13px;line-height:1.45}
.crm{--fs-body:13px;--fs-meta:12px;--fs-heading:13px;--fs-title:15px}

.crm .crm-bar { min-height: 44px; padding: 0 0 10px; margin-bottom: 16px; display: flex; align-items: center; flex-wrap: nowrap; }
.crm .page-context { display: flex; align-items: center; gap: 9px; min-width: 0; margin-right: auto; flex-basis: auto; }
.crm .page-context span { font-size: var(--fs-meta); line-height: var(--lh-meta); letter-spacing: 0; color: #5d6b64; }
.crm .page-context strong { font-size: var(--fs-heading); line-height: var(--lh-heading); font-weight: var(--fw-emphasis); color: #203c30; }
.account-menu { position: relative; flex-shrink: 0; }
.account-menu summary { list-style: none; cursor: pointer; border-radius: 50%; }
.account-menu summary::-webkit-details-marker { display: none; }
.account-menu summary > span { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 50%; background: #e4eee7; color: #234b37; border: 1px solid #cadbce; font-size: var(--fs-body); line-height: 1; font-weight: var(--fw-emphasis); }
.account-menu summary:focus-visible { outline: 2px solid #237356; outline-offset: 3px; }
.account-dropdown { position: absolute; right: 0; top: 53px; z-index: 30; width: 196px; border: 1px solid #dce5df; border-radius: 10px; padding: 6px; background: white; box-shadow: 0 8px 32px #17382b1a; }
.account-identity { padding: 9px 10px; margin-bottom: 4px; border-bottom: 1px solid #edf1ee; }
.account-identity strong, .account-identity small { display: block; font-size: var(--fs-body); line-height: var(--lh-body); }
.account-identity small { color: #5d6b64; font-size: var(--fs-meta); line-height: var(--lh-meta); }
.crm .account-dropdown button { width: 100%; display: block; text-align: left; background: white; color: #31483b; border: 0; border-radius: 6px; font-size: var(--fs-body); line-height: var(--lh-body); padding: 10px 10px; min-height: 44px; font-weight: var(--fw-body); }
.crm .account-dropdown button:hover { background: #edf5f1; }
@media(max-width:600px) { .crm .crm-bar { margin-bottom: 12px; } }
.desk-rail .rail-mobile-toggle{display:none}
@media(max-width:800px){.desk-rail .rail-mobile-toggle{display:flex;grid-column:1/-1}.desk-rail:not(.mobile-open)>button:not(.rail-mobile-toggle){display:none}.desk-rail{margin-bottom:10px!important}}
.crm.is-signed,.crm.is-signed.rail-collapsed { padding: 18px clamp(14px, 2vw, 32px) 36px; }
.top-nav { display:flex; align-items:center; gap:4px; min-height:60px; padding:8px 10px; margin:-18px calc(-1 * clamp(14px, 2vw, 32px)) 18px; background:#19392d; color:#e7eee9; overflow-x:auto; }
.top-nav .crm-brand { display:flex; flex:0 0 auto; align-items:center; justify-content:center; width:132px; min-height:44px; margin-right:8px; padding:4px 7px; border-radius:5px; background:#f8f8f4; }
.top-nav .crm-brand img { display:block; width:100%; max-height:40px; object-fit:contain; }
.top-nav>button { flex:0 0 auto; display:flex; align-items:center; justify-content:center; gap:8px; min-height:44px; padding:8px 11px; border:0; border-radius:7px; background:transparent; color:inherit; font-size:13px; white-space:nowrap; }
.top-nav>button:hover { background:#ffffff18; }
.top-nav>button.current { background:#315844; color:white; }
.top-nav .nav-brand { margin-right:auto; padding-inline:14px; font-size:16px; letter-spacing:.16em; font-weight:700; }
.top-nav .account-menu { margin-left:auto; position:sticky; right:0; background:#19392d; }
.top-nav .account-menu summary>span { background:#e4eee7; }
.crm-bar { min-height:38px; padding-bottom:8px; margin-bottom:16px; }
@media(max-width:800px) { .crm.is-signed,.crm.is-signed.rail-collapsed { padding:12px; } .top-nav { margin:-12px -12px 14px; gap:2px; } .top-nav .crm-brand { width:110px; margin-right:4px; } .top-nav>button { padding:8px; } .top-nav>button span { font-size:12px; } }
.nav-badge{display:inline-grid;place-items:center;min-width:17px;height:17px;padding:0 4px;border-radius:999px;background:#a34639;color:#fff;font-size:10px;font-weight:750;line-height:1}
</style>
