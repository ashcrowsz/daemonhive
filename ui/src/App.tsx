import { useEffect, useState } from 'react'
import { AppShell } from '@astryxdesign/core/AppShell'
import { SideNav, SideNavHeading, SideNavItem, SideNavSection } from '@astryxdesign/core/SideNav'
import { Text } from '@astryxdesign/core/Text'
import {
  ChatBubbleLeftRightIcon,
  ChartBarIcon,
  BoltIcon,
  ShareIcon,
  CpuChipIcon,
} from '@heroicons/react/24/outline'
import ChatPage from './pages/Chat'
import OverviewPage from './pages/Overview'
import TrainingPage from './pages/Training'
import MemoryPage from './pages/Memory'
import HivePage from './pages/Hive'

const PAGES = {
  chat: { label: 'Chat', icon: ChatBubbleLeftRightIcon, render: () => <ChatPage /> },
  overview: { label: 'Overview', icon: ChartBarIcon, render: () => <OverviewPage /> },
  training: { label: 'Training', icon: BoltIcon, render: () => <TrainingPage /> },
  memory: { label: 'Memory graph', icon: ShareIcon, render: () => <MemoryPage /> },
  hive: { label: 'Hive', icon: CpuChipIcon, render: () => <HivePage /> },
} as const
type PageId = keyof typeof PAGES

const fromHash = (): PageId => {
  const h = window.location.hash.replace('#', '')
  return (h in PAGES ? h : 'chat') as PageId
}

export default function App() {
  const [page, setPage] = useState<PageId>(fromHash)
  useEffect(() => {
    const on = () => setPage(fromHash())
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])

  return (
    <AppShell
      sideNav={
        <SideNav
          header={<SideNavHeading heading="Daemonhive" superheading="your agents" />}
          footer={
            <Text type="supporting" color="secondary">
              Local models · $0
            </Text>
          }>
          <SideNavSection title="Talk" isHeaderHidden>
            <SideNavItem
              label={PAGES.chat.label}
              icon={PAGES.chat.icon}
              href="#chat"
              isSelected={page === 'chat'}
            />
          </SideNavSection>
          <SideNavSection title="Your data">
            {(['overview', 'training', 'memory'] as const).map(id => (
              <SideNavItem
                key={id}
                label={PAGES[id].label}
                icon={PAGES[id].icon}
                href={`#${id}`}
                isSelected={page === id}
              />
            ))}
          </SideNavSection>
          <SideNavSection title="System">
            <SideNavItem label={PAGES.hive.label} icon={PAGES.hive.icon} href="#hive" isSelected={page === 'hive'} />
          </SideNavSection>
        </SideNav>
      }>
      {PAGES[page].render()}
    </AppShell>
  )
}
