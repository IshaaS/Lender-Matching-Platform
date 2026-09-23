import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ApplicationDetail } from './pages/ApplicationDetail'
import { ApplicationForm } from './pages/ApplicationForm'
import { ApplicationsList } from './pages/ApplicationsList'
import { Home } from './pages/Home'
import { LenderPolicy } from './pages/LenderPolicy'
import { LendersList } from './pages/LendersList'
import { RunResults } from './pages/RunResults'
import { Placeholder } from './pages/Placeholder'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="/applications" element={<ApplicationsList />} />
        <Route path="/applications/new" element={<ApplicationForm />} />
        <Route path="/applications/:id" element={<ApplicationDetail />} />
        <Route path="/applications/:id/edit" element={<ApplicationForm />} />
        <Route path="/applications/:id/runs/:runId" element={<RunResults />} />
        <Route path="/lenders" element={<LendersList />} />
        <Route path="/lenders/:id" element={<LenderPolicy />} />
        <Route path="*" element={<Placeholder title="Page not found" />} />
      </Route>
    </Routes>
  )
}
