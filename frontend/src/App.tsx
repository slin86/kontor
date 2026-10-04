import { Navigate, Route, Routes } from 'react-router-dom'

import { useAuth } from './auth'
import { Layout } from './components/Layout'
import { AuthPage } from './pages/AuthPage'
import { CashflowPage } from './pages/CashflowPage'
import { Placeholder } from './pages/Placeholder'

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
        <Route
          path="finanzierungen"
          element={<Placeholder title="Finanzierungen" text="Immobilienfinanzierungen, Bausparverträge und Kredite folgen in der nächsten Ausbaustufe." />}
        />
        <Route path="depot" element={<Placeholder title="Depot" text="Der Depotplan folgt in der nächsten Ausbaustufe." />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
