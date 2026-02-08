import { redirect } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import type { SessionSummaryRow } from '@/utils/types'
import DashboardClient from './dashboard-client'

export default async function DashboardPage() {
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) redirect('/login')

  const { data: sessions } = await supabase
    .from('session_summaries')
    .select('*')
    .eq('user_id', user.id)
    .order('created_at', { ascending: false })

  return (
    <DashboardClient
      sessions={(sessions as SessionSummaryRow[] | null) || []}
      userEmail={user.email || ''}
    />
  )
}
