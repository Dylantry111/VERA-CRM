<script setup lang="ts">
import ProductManager from "./ProductManager.vue";
const props = defineProps<{ admin: boolean }>();
const emit = defineEmits<{ updated: [] }>();
</script>

<template>
  <ProductManager :admin="props.admin" @updated="emit('updated')" />
</template>
