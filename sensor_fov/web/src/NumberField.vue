<script setup lang="ts">
defineProps<{ label: string; modelValue: number; min?: number; max?: number; step?: number }>()
const emit = defineEmits<{ 'update:modelValue': [value: number] }>()
function input(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement).valueAsNumber)
}
</script>
<template>
  <label class="field"><span>{{ label }}</span><input type="number" :aria-label="label" :value="Number.isFinite(modelValue) ? modelValue : ''" :min="min" :max="max" :step="step ?? 0.01" @input="input" /></label>
</template>
