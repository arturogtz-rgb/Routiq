import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useEffect } from 'react';
import '@/index.css';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import ProtectedRoute from '@/components/ProtectedRoute';
import { useSiteContent } from '@/lib/useSiteContent';
import { applyTheme } from '@/lib/theme';

import Landing from '@/pages/Landing';
import Login from '@/pages/Login';
import Signup from '@/pages/Signup';
import Dashboard from '@/pages/Dashboard';
import Kanban from '@/pages/Kanban';
import Packages from '@/pages/Packages';
import PackageEditor from '@/pages/PackageEditor';
import Services from '@/pages/Services';
import QuotationBuilder from '@/pages/QuotationBuilder';
import Clients from '@/pages/Clients';
import CustomQuotationBuilder from '@/pages/CustomQuotationBuilder';
import QuotationsList from '@/pages/QuotationsList';
import QuotationDetail from '@/pages/QuotationDetail';
import AuditLog from '@/pages/AuditLog';
import WhatsAppInbox from '@/pages/WhatsAppInbox';
import Team from '@/pages/Team';
import Settings from '@/pages/Settings';
import MasterAdmin, { MasterCompanies } from '@/pages/Master';
import MasterSite from '@/pages/MasterSite';
import MasterAI from '@/pages/MasterAI';
import PublicQuotation from '@/pages/PublicQuotation';
import PublicPackage from '@/pages/PublicPackage';
import PublicCatalog from '@/pages/PublicCatalog';
import Leads from '@/pages/Leads';
import CatalogAnalytics from '@/pages/CatalogAnalytics';
import SalesStats from '@/pages/SalesStats';
import { ConfirmProvider } from '@/components/ConfirmDialog';
import Profile from '@/pages/Profile';
import ForgotPassword from '@/pages/ForgotPassword';
import ResetPassword from '@/pages/ResetPassword';

function HomeRedirect() {
  const { user, loading } = useAuth();
  if (loading) return null;
  // Allow the Master "Vista previa" to render the live Landing even when logged in.
  const preview = new URLSearchParams(window.location.search).get('preview') === '1';
  if (!preview) {
    if (user && user.role === 'super_admin') return <Navigate to="/master" replace />;
    if (user) return <Navigate to="/app/dashboard" replace />;
  }
  return <Landing />;
}

function ThemeApplier() {
  const content = useSiteContent();
  useEffect(() => {
    if (content?.theme) applyTheme(content.theme);
  }, [content]);
  return null;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <ThemeApplier />
        <ConfirmProvider>
        <Routes>
          <Route path="/" element={<HomeRedirect />} />
          <Route path="/login" element={<Login />} />
          <Route path="/signup" element={<Signup />} />
          <Route path="/forgot-password" element={<ForgotPassword />} />
          <Route path="/reset-password" element={<ResetPassword />} />
          <Route path="/q/:token" element={<PublicQuotation />} />
          <Route path="/p/:slug/:code" element={<PublicPackage />} />
          <Route path="/c/:slug" element={<PublicCatalog />} />

          {/* Company app */}
          <Route path="/app/dashboard" element={<ProtectedRoute roles={['company_admin', 'executive']}><Dashboard /></ProtectedRoute>} />
          <Route path="/app/kanban" element={<ProtectedRoute roles={['company_admin', 'executive']}><Kanban /></ProtectedRoute>} />
          <Route path="/app/packages" element={<ProtectedRoute roles={['company_admin', 'executive']}><Packages /></ProtectedRoute>} />
          <Route path="/app/packages/new" element={<ProtectedRoute roles={['company_admin']}><PackageEditor /></ProtectedRoute>} />
          <Route path="/app/packages/:id/edit" element={<ProtectedRoute roles={['company_admin']}><PackageEditor /></ProtectedRoute>} />
          <Route path="/app/services" element={<ProtectedRoute roles={['company_admin', 'executive']}><Services /></ProtectedRoute>} />
          <Route path="/app/quotations" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationsList /></ProtectedRoute>} />
          <Route path="/app/leads" element={<ProtectedRoute roles={['company_admin', 'executive']}><Leads /></ProtectedRoute>} />
          <Route path="/app/analytics" element={<ProtectedRoute roles={['company_admin']}><CatalogAnalytics /></ProtectedRoute>} />
          <Route path="/app/stats" element={<ProtectedRoute roles={['company_admin']}><SalesStats /></ProtectedRoute>} />
          <Route path="/app/quotations/new" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationBuilder /></ProtectedRoute>} />
          <Route path="/app/clients" element={<ProtectedRoute roles={['company_admin', 'executive']}><Clients /></ProtectedRoute>} />
          <Route path="/app/quotations/new/custom" element={<ProtectedRoute roles={['company_admin', 'executive']}><CustomQuotationBuilder /></ProtectedRoute>} />
          <Route path="/app/quotations/custom/:id/edit" element={<ProtectedRoute roles={['company_admin', 'executive']}><CustomQuotationBuilder /></ProtectedRoute>} />
          <Route path="/app/quotations/:id/edit" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationBuilder /></ProtectedRoute>} />
          <Route path="/app/quotations/:id" element={<ProtectedRoute roles={['company_admin', 'executive']}><QuotationDetail /></ProtectedRoute>} />
          <Route path="/app/audit" element={<ProtectedRoute roles={['company_admin']}><AuditLog /></ProtectedRoute>} />
          <Route path="/app/whatsapp" element={<ProtectedRoute roles={['company_admin', 'executive']}><WhatsAppInbox /></ProtectedRoute>} />
          <Route path="/app/team" element={<ProtectedRoute roles={['company_admin']}><Team /></ProtectedRoute>} />
          <Route path="/app/settings" element={<ProtectedRoute roles={['company_admin']}><Settings /></ProtectedRoute>} />
          <Route path="/profile" element={<ProtectedRoute roles={['company_admin', 'executive', 'super_admin']}><Profile /></ProtectedRoute>} />

          {/* Master panel */}
          <Route path="/master" element={<ProtectedRoute roles={['super_admin']}><MasterAdmin /></ProtectedRoute>} />
          <Route path="/master/companies" element={<ProtectedRoute roles={['super_admin']}><MasterCompanies /></ProtectedRoute>} />
          <Route path="/master/ai" element={<ProtectedRoute roles={['super_admin']}><MasterAI /></ProtectedRoute>} />
          <Route path="/master/site" element={<ProtectedRoute roles={['super_admin']}><MasterSite /></ProtectedRoute>} />

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
        </ConfirmProvider>
      </BrowserRouter>
    </AuthProvider>
  );
}
