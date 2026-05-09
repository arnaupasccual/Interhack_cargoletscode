<script setup>
import { RouterView, RouterLink } from 'vue-router'
</script>

<template>
  <div class="app-layout">
    <header class="app-header">
      <div class="header-inner">
        <RouterLink to="/alerts" class="brand">
          <span class="brand-icon">⚡</span>
          Alert Dashboard
        </RouterLink>
        <nav class="header-nav">
          <RouterLink to="/alerts" class="nav-link">Alerts</RouterLink>
        </nav>
      </div>
    </header>

    <main class="app-main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background: #f4f6f9;
}

.app-header {
  background: #1a1f2e;
  color: #fff;
  padding: 0 2rem;
  height: 56px;
  display: flex;
  align-items: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,.25);
}

.header-inner {
  display: flex;
  align-items: center;
  gap: 2rem;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
}

.brand {
  display: flex;
  align-items: center;
  gap: .5rem;
  font-size: 1.1rem;
  font-weight: 700;
  color: #fff;
  text-decoration: none;
  letter-spacing: .3px;
}
.brand-icon { font-size: 1.2rem; }

.header-nav { display: flex; gap: 1.5rem; margin-left: auto; }

.nav-link {
  color: #a0aec0;
  text-decoration: none;
  font-size: .9rem;
  transition: color .15s;
}
.nav-link:hover,
.nav-link.router-link-active { color: #fff; }

.app-main {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}
</style>
