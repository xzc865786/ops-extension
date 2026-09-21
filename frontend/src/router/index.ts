import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory('/ext/app/'),
  routes: [
    { path: '/', redirect: '/tickets' },
    {
      path: '/tickets',
      name: 'tickets',
      component: () => import('@/views/tickets/TicketList.vue'),
    },
    {
      path: '/tickets/new',
      name: 'ticket-new',
      component: () => import('@/views/tickets/TicketCreate.vue'),
    },
    {
      path: '/tickets/:id',
      name: 'ticket-detail',
      component: () => import('@/views/tickets/TicketDetail.vue'),
    },
    {
      path: '/admin/tickets',
      name: 'admin-tickets',
      meta: { admin: true },
      component: () => import('@/views/admin/tickets/AdminTicketList.vue'),
    },
    {
      path: '/admin/tickets/:id',
      name: 'admin-ticket-detail',
      meta: { admin: true },
      component: () => import('@/views/admin/tickets/AdminTicketDetail.vue'),
    },
    {
      path: '/admin/expenses',
      name: 'admin-expenses',
      meta: { admin: true },
      component: () => import('@/views/admin/expenses/ExpenseList.vue'),
    },
    {
      path: '/admin/expenses/new',
      name: 'admin-expense-new',
      meta: { admin: true },
      component: () => import('@/views/admin/expenses/ExpenseForm.vue'),
    },
    {
      path: '/admin/expenses/:id',
      name: 'admin-expense-detail',
      meta: { admin: true },
      component: () => import('@/views/admin/expenses/ExpenseDetail.vue'),
    },
    {
      path: '/admin/suppliers',
      name: 'admin-suppliers',
      meta: { admin: true },
      component: () => import('@/views/admin/expenses/Masters.vue'),
    },
    {
      path: '/admin/cost-centers',
      redirect: '/admin/suppliers',
    },
    {
      path: '/admin/payment-accounts',
      redirect: '/admin/suppliers',
    },
    {
      path: '/admin/reports',
      name: 'admin-reports',
      meta: { admin: true },
      component: () => import('@/views/admin/reports/ReportDashboard.vue'),
    },
    {
      path: '/auth/error',
      component: () => import('@/views/auth/AuthError.vue'),
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) await auth.fetchMe()
  if (!auth.me && to.path !== '/auth/error') {
    // allow viewing error page; otherwise show error
    return { path: '/auth/error', query: { reason: 'unauthenticated' } }
  }
  if (to.meta.admin && !auth.isAdmin) {
    return { path: '/tickets' }
  }
})

export default router
