<script setup>
import { RouterView, RouterLink, useRoute } from 'vue-router'

const route = useRoute()
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-brand">
        <span class="brand-name">SigSer</span>
      </div>
      <nav class="sidebar-nav">
        <RouterLink to="/" class="nav-link" :class="{ active: route.path === '/' }">
          <span class="nav-icon">◼</span>
          Dashboard
        </RouterLink>
        <RouterLink to="/alerts" class="nav-link" :class="{ active: route.path.startsWith('/alerts') }">
          <span class="nav-icon">◼</span>
          Alerts
        </RouterLink>
      </nav>
    </aside>
    <main class="main-content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  min-height: 100vh;
}

.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--sidebar-bg);
  display: flex;
  flex-direction: column;
  padding: 0;
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  z-index: 10;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 24px 20px 20px;
  border-bottom: 1px solid rgba(255,255,255,0.08);
}

.brand-icon { font-size: 20px; }
.brand-name {
  font-size: 15px;
  font-weight: 700;
  color: #fff;
  letter-spacing: -0.01em;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  padding: 16px 10px;
  gap: 2px;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: 8px;
  color: rgba(255,255,255,0.6);
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, color 0.15s;
}

.nav-link:hover { background: rgba(255,255,255,0.08); color: #fff; }
.nav-link.active { background: rgba(255,255,255,0.14); color: #fff; }
.nav-icon { font-size: 8px; }

.main-content {
  margin-left: 220px;
  flex: 1;
  padding: 32px;
  min-height: 100vh;
  background: var(--page-bg);
}
</style>
