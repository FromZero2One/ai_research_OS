<script setup lang="ts">
import Sidebar from '@/components/Sidebar.vue'
import CommandPalette from '@/components/CommandPalette.vue'
</script>

<template>
  <div class="layout">
    <Sidebar />
    <main class="main-content">
      <router-view />
    </main>
    <CommandPalette />
  </div>
</template>

<style>
.layout {
  display: flex;
  min-height: 100vh;
}
.main-content {
  flex: 1;
  padding: 32px;
  overflow: auto;
  max-width: 1200px;
  margin: 0 auto;
  width: 0;
  min-width: 0;
}
</style>
