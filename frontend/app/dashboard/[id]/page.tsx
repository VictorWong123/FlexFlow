import { redirect, notFound } from 'next/navigation'
import { createClient } from '@/utils/supabase/server'
import type { SessionSummaryRow } from '@/utils/types'
import SessionDetailClient from './session-detail-client'

interface PageProps {
  params: Promise<{ id: string }>
}

export default async function SessionDetailPage({ params }: PageProps) {
  const { id } = await params
  const supabase = await createClient()

  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) redirect('/login')

  const { data: session } = await supabase
    .from('session_summaries')
    .select('*')
    .eq('id', id)
    .eq('user_id', user.id)
    .single()

  if (!session) notFound()

  return <SessionDetailClient session={session as SessionSummaryRow} />
}
