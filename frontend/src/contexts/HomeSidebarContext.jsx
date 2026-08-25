import { createContext, useContext } from 'react'

export const HomeSidebarContext = createContext({
  isOpen: false,
  toggle: () => {},
  close: () => {},
})

export const HomeNavigationContext = createContext({
  isAdmin: false,
  isAuthenticated: false,
  user: null,
})

export function useHomeSidebar() {
  return useContext(HomeSidebarContext)
}

export function useHomeNavigation() {
  return useContext(HomeNavigationContext)
}
