import { createContext, useContext, useEffect, useState } from 'react';
import { apiRequest, clearToken, getToken, onUnauthorized, setToken } from './api';

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(Boolean(getToken()));

  useEffect(() => {
    const stop = onUnauthorized(() => setUser(null));
    if (!getToken()) return stop;
    const controller = new AbortController();
    apiRequest('/auth/me', { signal: controller.signal })
      .then(me => { if (!controller.signal.aborted) setUser(me); })
      .catch(() => { if (!controller.signal.aborted) clearToken(); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); stop(); };
  }, []);

  async function authenticate(path, data) {
    const result = await apiRequest(path, { method: 'POST', data });
    setToken(result.token);
    setUser(result.user);
  }
  const value = {
    user, loading,
    login: (email, password) => authenticate('/auth/login', { email, password }),
    register: (name, email, password) => authenticate('/auth/register', { name, email, password }),
    logout: () => { clearToken(); setUser(null); },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
