import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth'
import { Layout } from './components/Layout'
import { AuthPage } from './pages/AuthPage'
import { AccountPage } from './pages/AccountPage'
import { WealthPage } from './pages/WealthPage'
import { PropertiesPage } from './pages/PropertiesPage'
import { ActualPage } from './pages/ActualPage'
import { CashflowShell } from './pages/cashflow/CashflowShell'
import { DetailsView } from './pages/cashflow/DetailsView'
import { ItemsView } from './pages/cashflow/ItemsView'
import { OverviewView } from './pages/cashflow/OverviewView'
import { CategoriesPage } from './pages/CategoriesPage'
import { DepotPage } from './pages/DepotPage'
import { DepotOverview } from './pages/depot/DepotOverview'
import { DepotShell } from './pages/depot/DepotShell'
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
        <Route element={<CashflowShell />}>
          <Route index element={<OverviewView />} />
          <Route path="details" element={<DetailsView />} />
          <Route path="posten" element={<ItemsView />} />
        </Route>
        <Route path="kategorien" element={<CategoriesPage />} />
        <Route path="finanzierungen" element={<FinancingsPage />} />
        <Route path="depot" element={<DepotShell />}>
          <Route index element={<DepotOverview />} />
          <Route path="plan" element={<DepotPage />} />
          <Route path="ist" element={<ActualPage />} />
          <Route path="fonds" element={<InstrumentsPage />} />
        </Route>
        <Route path="ist" element={<Navigate to="/depot/ist" replace />} />
        <Route path="instrumente" element={<Navigate to="/depot/fonds" replace />} />
        <Route path="vermoegen" element={<WealthPage />} />
        <Route path="immobilien" element={<PropertiesPage />} />
        <Route path="konto" element={<AccountPage />} />
        <Route path="haushalt" element={<HouseholdPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
