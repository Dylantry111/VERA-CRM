<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import ProductManager from "./ProductManager.vue";
import PricingKnowledge from "./PricingKnowledge.vue";

const props = defineProps<{ admin: boolean }>();
const emit = defineEmits<{ updated: [] }>();
const { locale } = useI18n();
const tx = (zh: string, en: string) => locale.value === "zh" ? zh : en;
const area = ref<"catalog" | "pricing">("catalog");
const productCode = ref("");
function openPricing(code: string) {
  productCode.value = code;
  area.value = "pricing";
}
watch(() => props.admin, () => { if (!props.admin) area.value = "catalog"; });
</script>

<template>
  <section class="product-workspace">
    <nav class="workspace-tabs" role="tablist" :aria-label="tx('产品工作区','Product workspace')">
      <button type="button" role="tab" :aria-selected="area==='catalog'" :class="{active:area==='catalog'}" @click="area='catalog'">{{ tx("产品目录", "Product catalogue") }}</button>
      <button type="button" role="tab" :aria-selected="area==='pricing'" :class="{active:area==='pricing'}" @click="area='pricing'">{{ tx("产品价格与计算", "Product pricing & calculation") }}</button>
    </nav>
    <ProductManager v-if="area==='catalog'" :admin="admin" @updated="emit('updated')" @pricing="openPricing" />
    <PricingKnowledge v-else :admin="admin" :product-code="productCode" />
  </section>
</template>

<style scoped>
.workspace-tabs{display:flex;gap:8px;margin:0 0 18px;padding:0 0 10px;border-bottom:1px solid rgba(53,69,82,.18);overflow:auto}
.workspace-tabs button{min-height:38px;padding:8px 15px;border:1px solid #c7d3d8;border-radius:999px;background:#fff;color:#354552;font-size:13px;font-weight:650;white-space:nowrap;cursor:pointer}
.workspace-tabs button.active{background:#354552;color:#fff;border-color:#354552}
.workspace-tabs button:hover:not(.active){background:#e8eef0;border-color:#8a9ca5}
</style>
