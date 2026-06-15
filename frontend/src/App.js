import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import '@/index.css';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';

import Landing from '@/pages/Landing';
import Login from '@/pages/Login';
import Dashboard from '@/pages/Dashboard';
import Kanban from '@/pages/Kanban';
import Packages from '@/pages/Packages';
import Services from '@/pages/Services';
import QuotationBuilder from '@/pages/QuotationBuilder';
import QuotationsList from '@/pages/QuotationsList';
import QuotationDetail from '@/pages/QuotationDetail';
import WhatsAppInbox from '@/pages/WhatsAppInbox';
import Team from '@/pages/Team';
import Settings from '@/pages/Settings';
import MasterAdmin, { MasterCompanies } from '@/pages/Master';
import PublicQuotation from '@/pages/PublicQuotation';

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (user && user.role === 'super_admin') return <Navigate to="/master" replace />;
  if (user) return <Navigate to="/app/dashboard" replace />;
  return <Landing />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/q/:token" element={<PublicQuotation />} />

          {/* Company app */}
          <Route path="/app/dashboard" element={<ProtectedRoute roles={['company_admin', 'executive']}><Dashboard /></ProtectedRoute>} />
          <Route path="/app/kanban" element={<ProtectedRoute roles={['company_admin', 'executive']}><Kanban /></ProtectedRoute>} />
          <Route path="/app/packages" element={<ProtectedRoute roles={['company_admin', 'executive']}><Packages /></ProtectedRoute>} />
          <Route path="/app/services" element={<ProtectedRoute roles={['company_admin', 'executive']}><Services /></ProtectedRoute>} />
          <Route path="/app/quotations" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationsList /></ProtectedRoute>} />
          <Route path="/app/quotations/new" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationBuilder /></ProtectedRoute>} />
          <Route path="/app/quotations/:id" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationDetail /></ProtectedRoute>} />
          <Route path="/app/whatsapp" element={<ProtectedRoute roles={['company_admin', 'executive']}><WhatsAppInbox /></ProtectedRoute>} />
          <Route path="/app/team" element={<ProtectedRoute roles={['company_admin']}><Team /></ProtectedRoute>} />
          <Route path="/app/settings" element={<ProtectedRoute roles={['company_admin']}><Settings /></ProtectedRoute>} />

          {/* Master panel */}
          <Route path="/master" element={<ProtectedRoute roles={['super_admin']}><MasterAdmin /></ProtectedRoute>} />
          <Route path="/master/companies" element={<ProtectedRoute roles={['super_admin']}><MasterCompanies /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
