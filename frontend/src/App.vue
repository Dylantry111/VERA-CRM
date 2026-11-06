<script setup lang="ts">
import { computed, ref, onMounted, onBeforeUnmount, watch } from "vue";
import { useRoute } from "vue-router";
import { useI18n } from "vue-i18n";
import SiteFooter from "./components/SiteFooter.vue";

const { t, locale } = useI18n();
const route = useRoute();
const workbench = computed(() => route.path.startsWith("/crm"));
const portalWorkspace = computed(() => route.path.startsWith("/portal"));
const menuOpen = ref(false);
const home = computed(() => route.path === '/');
const scrolled = ref(false);
function updateScroll(){scrolled.value=window.scrollY>24}
onMounted(()=>{updateScroll();window.addEventListener('scroll',updateScroll,{passive:true})});
onBeforeUnmount(()=>window.removeEventListener('scroll',updateScroll));
watch(()=>route.path,()=>{menuOpen.value=false;updateScroll()});

function toggleLocale() {
  const next = locale.value === "zh" ? "en" : "zh";
  locale.value = next;
  localStorage.setItem("vera-locale", next);
  document.documentElement.lang = next === "zh" ? "zh" : "en";
}
</script>

<template>
  <div class="frame" :class="{ 'frame-work': workbench, 'frame-portal': portalWorkspace }">
    <header v-if="!workbench" class="rail" :class="{'rail-home':home,'rail-solid':scrolled||menuOpen}" >
      <router-link to="/" class="mark">
        <img class="brand-logo" src="/images/vera-logo.png" alt="VERA Shading Solutions" />
      </router-link>
      <button type="button" class="secondary menu" :aria-expanded="menuOpen" aria-controls="site-navigation" @click="menuOpen = !menuOpen">
        {{ t("nav.menu") }}
      </button>
      <nav id="site-navigation" class="nav" :class="{ open: menuOpen }">
        <router-link to="/">{{ t("nav.home") }}</router-link>
        <router-link to="/products">{{ t("nav.products") }}</router-link>
        <router-link to="/about">{{ t("nav.about") }}</router-link>
        <router-link to="/portal" class="nav-quote">{{ t("nav.portal") }}</router-link>
        <router-link to="/contact">{{ t("nav.contact") }}</router-link>
      </nav>
      <button type="button" class="secondary" @click="toggleLocale">
        {{ t("switchTo") }}
      </button>
    </header>
    <router-view />
    <SiteFooter v-if="!workbench && !portalWorkspace" />

  </div>
</template>

<style scoped>
.rail{min-height:76px}
.rail:not(.rail-home){background:#faf9f6}
@media(max-width:700px){.rail{min-height:72px;padding-top:12px;padding-bottom:12px}}
.rail-home{position:fixed;left:0;right:0;top:0;z-index:50;background:rgba(250,249,246,.97);color:var(--ink);border-bottom:1px solid var(--line)}
.brand-logo{display:block;width:170px;height:auto;max-height:58px;object-fit:contain}
.nav a.router-link-active:not(.button){box-shadow:none}.nav-quote{background:transparent;border:0;color:inherit}
@media(max-width:700px){.brand-logo{width:148px;max-height:50px}}

.frame-portal .rail{min-height:64px;padding:8px 24px;border-bottom:1px solid var(--line)}
.frame-portal .brand-logo{width:150px;max-height:52px}
@media(max-width:700px){.frame-portal .rail{min-height:60px;padding:6px 12px}}

.frame-portal{padding:0;display:flex;flex-direction:column;min-height:100dvh}.frame-portal .rail{flex:none}
.frame-work{margin:0;padding:0}
</style>
