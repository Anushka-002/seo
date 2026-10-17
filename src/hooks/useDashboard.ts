import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { deleteAnalysis, getDashboardStats, listAnalyses } from '@/lib/api'
import type { ListParams } from '@/lib/types'

export const useDashboardStats = () =>
  useQuery({ queryKey: ['dashboard-stats'], queryFn: getDashboardStats })

export const useHistory = (params: ListParams) =>
  useQuery({
    queryKey: ['history', params],
    queryFn: () => listAnalyses(params),
    placeholderData: keepPreviousData,
  })

/** Delete one analysis, then refresh the history table and the stats. */
export function useDeleteAnalysis(onDone?: () => void, onError?: (message: string) => void) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: deleteAnalysis,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['history'] })
      void qc.invalidateQueries({ queryKey: ['dashboard-stats'] })
      onDone?.()
    },
    onError: (e: Error) => onError?.(e.message),
  })
}
