export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {
  public: {
    Tables: {
      session_summaries: {
        Row: {
          id: string
          user_id: string
          session_key: string
          schema_version: number
          summary_text: string
          pain_points: string[]
          stretches_performed: string[]
          youtube_links: Json
          duration_seconds: number
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          session_key?: string
          schema_version?: number
          summary_text: string
          pain_points?: string[]
          stretches_performed?: string[]
          youtube_links?: Json
          duration_seconds?: number
          created_at?: string
        }
        Update: Partial<Database['public']['Tables']['session_summaries']['Insert']>
        Relationships: []
      }
      therapy_sessions: {
        Row: {
          id: string
          user_id: string
          room_name: string
          status: 'active' | 'summarizing' | 'completed' | 'expired' | 'failed'
          created_at: string
          updated_at: string
          expires_at: string
        }
        Insert: {
          id: string
          user_id: string
          room_name: string
          status?: 'active' | 'summarizing' | 'completed' | 'expired' | 'failed'
          created_at?: string
          updated_at?: string
          expires_at: string
        }
        Update: Partial<Database['public']['Tables']['therapy_sessions']['Insert']>
        Relationships: []
      }
    }
    Views: Record<string, never>
    Functions: {
      issue_therapy_session: {
        Args: { p_session_id: string; p_room_name: string; p_expires_at: string }
        Returns: { id: string; room_name: string; status: string; expires_at: string }[]
      }
      claim_therapy_session: { Args: { p_session_id: string }; Returns: string }
      delete_session_summary: { Args: { p_summary_id: string }; Returns: boolean }
      close_therapy_session: { Args: { p_session_id: string }; Returns: boolean }
      release_therapy_session: { Args: { p_session_id: string; p_failed: boolean }; Returns: boolean }
      complete_therapy_session: {
        Args: {
          p_session_id: string; p_summary_text: string; p_pain_points: string[]
          p_stretches_performed: string[]; p_youtube_links: Json; p_duration_seconds: number
        }
        Returns: string
      }
    }
    Enums: Record<string, never>
    CompositeTypes: Record<string, never>
  }
}
