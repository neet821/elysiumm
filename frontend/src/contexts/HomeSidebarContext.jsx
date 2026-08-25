import { createContext, useContext } from 'react'

export const HomeSidebarContext = createContext({
  isOpen: false,
  toggle: () => {},
  close: () => {},
})

export function useHomeSidebar() {
  return useContext(HomeSidebarContext)
}
