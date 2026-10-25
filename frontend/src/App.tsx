import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { getAuthToken, setAuthToken } from "./api";
import AuthPage from "./pages/Auth";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Jobs from "./pages/Jobs";
import RepoPage from "./pages/RepoPage";
import Repositories from "./pages/Repositories";

export default function App() {
  const [token, setToken] = useState(getAuthToken);

  useEffect(() => {
    const signOut = () => setToken(null);
    window.addEventListener("lci:unauthorized", signOut);
    return () => window.removeEventListener("lci:unauthorized", signOut);
  }, []);

  const handleSignOut = () => {
    setAuthToken(null);
    setToken(null);
  };

  if (!token) {
    return <AuthPage onAuthenticated={(accessToken) => {
      setAuthToken(accessToken);
      setToken(accessToken);
    }} />;
  }

  return (
    <Layout onSignOut={handleSignOut}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/repositories" element={<Repositories />} />
        <Route path="/repositories/:id" element={<RepoPage />} />
        <Route path="/jobs" element={<Jobs />} />
        <Route path="*" element={<p className="p-10 text-slate-500">Page not found.</p>} />
      </Routes>
    </Layout>
  );
}
