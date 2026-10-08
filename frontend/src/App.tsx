import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth'
import { Layout } from './components/Layout'
import { AuthPage } from './pages/AuthPage'
import { AccountPage } from './pages/AccountPage'
import { ActualPage } from './pages/ActualPage'
import { CashflowPage } from './pages/CashflowPage'
import { CategoriesPage } from './pages/CategoriesPage'
import { DepotPage } from './pages/DepotPage'
import { FinancingsPage } from './pages/FinancingsPage'
import { HouseholdPage } from './pages/HouseholdPage'
import { InstrumentsPage } from './pages/InstrumentsPage'

function RequireAuth({ children }: { children: React.ReactNode }) {
  const { me, loading } = useAuth()
  if (loading) return null
  if (!me) return <Navigate to="/anmelden" replace />
  return <>{children}</>
}

export default function App() {
  return (
    <Routes>
      <Route path="/anmelden" element={<AuthPage />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<CashflowPage />} />
        <Route path="kategorien" element={<CategoriesPage />} />
        <Route path="finanzierungen" element={<FinancingsPage />} />
        <Route path="depot" element={<DepotPage />} />
        <Route path="ist" element={<ActualPage />} />
        <Route path="instrumente" element={<InstrumentsPage />} />
        <Route path="konto" element={<AccountPage />} />
        <Route path="haushalt" element={<HouseholdPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
