/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import * as authService from '../services/authService';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => localStorage.getItem('access_token'));
  const [username, setUsername] = useState(() => localStorage.getItem('username'));

  const isAuthenticated = !!token;

  const login = useCallback(async (user, password) => {
    const data = await authService.login(user, password);
    const accessToken = data.access_token;
    localStorage.setItem('access_token', accessToken);
    localStorage.setItem('username', user);
    setToken(accessToken);
    setUsername(user);
    return data;
  }, []);

  const register = useCallback(async (user, password) => {
    const data = await authService.register(user, password);
    return data;
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('username');
    setToken(null);
    setUsername(null);
  }, []);

  const value = useMemo(
    () => ({ token, username, isAuthenticated, login, register, logout }),
    [token, username, isAuthenticated, login, register, logout]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
}
