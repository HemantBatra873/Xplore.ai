import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import type { User } from '@/types'

interface AuthContextType {
  token: string | null
  user: User | null
  isAuthenticated: boolean
  login: (token: string, user: User) => void
  logout: () => void
  setUser: (user: User) => void
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('xplore_token'))
  const [user, setUser] = useState<User | null>(() => {
    try {
      const stored = localStorage.getItem('xplore_user')
      return stored ? JSON.parse(stored) : null
    } catch {
      localStorage.removeItem('xplore_user')
      return null
    }
  })

  const login = useCallback((newToken: string, newUser: User) => {
    localStorage.setItem('xplore_token', newToken)
    localStorage.setItem('xplore_user', JSON.stringify(newUser))
    setToken(newToken)
    setUser(newUser)
  }, [])

  const logout = useCallback(() => {
    localStorage.removeItem('xplore_token')
    localStorage.removeItem('xplore_user')
    setToken(null)
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        isAuthenticated: !!token,
        login,
        logout,
        setUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
