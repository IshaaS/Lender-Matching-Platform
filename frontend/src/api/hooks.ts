import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, api } from './client'
import type {
  Application,
  ApplicationListItem,
  ApplicationPayload,
  Catalog,
  FeatureSet,
  IngestionJob,
  Lender,
  MatchResultDetail,
  PolicyVersion,
  PolicyVersionSummary,
  Program,
  ProgramIn,
  Rule,
  RuleInput,
  Run,
  SampleApplication,
} from './types'

const json = (body: unknown): RequestInit => ({ body: JSON.stringify(body) })

export const keys = {
  applications: ['applications'] as const,
  application: (id: string) => ['applications', id] as const,
  features: (id: string) => ['applications', id, 'features'] as const,
  runs: (id: string) => ['applications', id, 'runs'] as const,
  run: (id: string) => ['runs', id] as const,
  result: (id: string) => ['results', id] as const,
  lenders: ['lenders'] as const,
  lender: (id: string) => ['lenders', id] as const,
  versions: (id: string) => ['lenders', id, 'versions'] as const,
  version: (id: string) => ['policy-versions', id] as const,
  ingestion: ['ingestion'] as const,
  ingestionJob: (id: string) => ['ingestion', id] as const,
}

const isActive = (status: string | undefined) => status === 'queued' || status === 'running'

// Poll while the application says underwriting too: if a run finishes between the two reads
// that build a response, the next poll reconciles instead of leaving a stale badge on screen.
const isBusy = (data: { status?: string; latest_run?: { status: string } | null } | undefined) =>
  data?.status === 'underwriting' || isActive(data?.latest_run?.status)

// --- reference data: effectively static, so cache for the session -----------------------------

export const useCatalog = () =>
  useQuery({ queryKey: ['catalog'], queryFn: () => api<Catalog>('/catalog'), staleTime: Infinity })

export const useSamples = () =>
  useQuery({
    queryKey: ['samples'],
    queryFn: () => api<SampleApplication[]>('/samples'),
    staleTime: Infinity,
  })

// --- applications ---------------------------------------------------------------------------

export const useApplications = () =>
  useQuery({
    queryKey: keys.applications,
    queryFn: () => api<ApplicationListItem[]>('/applications'),
    refetchInterval: (query) => (query.state.data?.some(isBusy) ? 2000 : false),
  })

export const useApplication = (id: string | undefined) =>
  useQuery({
    queryKey: keys.application(id ?? ''),
    queryFn: () => api<Application>(`/applications/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (isBusy(query.state.data) ? 1500 : false),
  })

export const useFeatures = (id: string) =>
  useQuery({
    queryKey: keys.features(id),
    queryFn: () => api<FeatureSet>(`/applications/${id}/features`),
  })

export const useRuns = (id: string) =>
  useQuery({ queryKey: keys.runs(id), queryFn: () => api<Run[]>(`/applications/${id}/runs`) })

export const useRun = (runId: string | undefined) =>
  useQuery({
    queryKey: keys.run(runId ?? ''),
    queryFn: () => api<Run>(`/runs/${runId}`),
    enabled: Boolean(runId),
    refetchInterval: (query) => (isActive(query.state.data?.status) ? 1500 : false),
  })

/** Full criterion-by-criterion breakdown for one lender; loaded when a lender is opened. */
export const useResult = (resultId: string | undefined) =>
  useQuery({
    queryKey: keys.result(resultId ?? ''),
    queryFn: () => api<MatchResultDetail>(`/results/${resultId}`),
    enabled: Boolean(resultId),
    staleTime: Infinity, // results are immutable once written
  })

export function useSaveApplication(id: string | undefined) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (payload: ApplicationPayload) =>
      id
        ? api<Application>(`/applications/${id}`, { method: 'PUT', ...json(payload) })
        : api<Application>('/applications', { method: 'POST', ...json(payload) }),
    onSuccess: (saved) => {
      client.setQueryData(keys.application(saved.id), saved)
      void client.invalidateQueries({ queryKey: keys.applications })
    },
  })
}

function useApplicationAction<T>(id: string, path: string, method: 'POST' | 'DELETE') {
  const client = useQueryClient()
  return useMutation({
    mutationFn: () => api<T>(`/applications/${id}${path}`, { method }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.applications }),
  })
}

export const useSubmitApplication = (id: string) =>
  useApplicationAction<Application>(id, '/submit', 'POST')
export const useDuplicateApplication = (id: string) =>
  useApplicationAction<Application>(id, '/duplicate', 'POST')
export const useDeleteApplication = (id: string) => useApplicationAction<void>(id, '', 'DELETE')
export const useStartRun = (id: string) => useApplicationAction<Run>(id, '/runs', 'POST')

// --- lender policies -------------------------------------------------------------------------

export const useLenders = () =>
  useQuery({ queryKey: keys.lenders, queryFn: () => api<Lender[]>('/lenders') })

export const useLender = (id: string | undefined) =>
  useQuery({
    queryKey: keys.lender(id ?? ''),
    queryFn: () => api<Lender>(`/lenders/${id}`),
    enabled: Boolean(id),
  })

export const usePolicyVersion = (id: string | undefined) =>
  useQuery({
    queryKey: keys.version(id ?? ''),
    queryFn: () => api<PolicyVersion>(`/policy-versions/${id}`),
    enabled: Boolean(id),
  })

export const useVersionHistory = (lenderId: string | undefined) =>
  useQuery({
    queryKey: keys.versions(lenderId ?? ''),
    queryFn: () => api<PolicyVersionSummary[]>(`/lenders/${lenderId}/versions`),
    enabled: Boolean(lenderId),
  })

/** Policy edits always land on a draft, so every mutation refreshes that draft and the list. */
function usePolicyMutation<TArgs, TResult>(
  lenderId: string,
  versionId: string | undefined,
  request: (args: TArgs) => Promise<TResult>,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      if (versionId) void client.invalidateQueries({ queryKey: keys.version(versionId) })
      void client.invalidateQueries({ queryKey: keys.lenders })
      void client.invalidateQueries({ queryKey: keys.lender(lenderId) })
      void client.invalidateQueries({ queryKey: keys.versions(lenderId) })
    },
  })
}

export const useCreateDraft = (lenderId: string) =>
  usePolicyMutation(lenderId, undefined, () =>
    api<PolicyVersion>(`/lenders/${lenderId}/draft`, { method: 'POST' }),
  )

export const usePublishVersion = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, () =>
    api<PolicyVersion>(`/policy-versions/${versionId}/publish`, { method: 'POST' }),
  )

export const useDiscardDraft = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, () =>
    api<void>(`/policy-versions/${versionId}`, { method: 'DELETE' }),
  )

export const useSaveRule = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, ({ id, ...rule }: RuleInput & { id?: string }) =>
    id
      ? api<Rule>(`/rules/${id}`, { method: 'PUT', ...json(rule) })
      : api<Rule>(`/policy-versions/${versionId}/rules`, { method: 'POST', ...json(rule) }),
  )

export const useDeleteRule = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, (ruleId: string) =>
    api<void>(`/rules/${ruleId}`, { method: 'DELETE' }),
  )

export const useSaveProgram = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, ({ id, ...program }: ProgramIn & { id?: string }) =>
    id
      ? api<Program>(`/programs/${id}`, { method: 'PATCH', ...json(program) })
      : api<Program>(`/policy-versions/${versionId}/programs`, { method: 'POST', ...json(program) }),
  )

export const useDeleteProgram = (lenderId: string, versionId: string) =>
  usePolicyMutation(lenderId, versionId, (programId: string) =>
    api<void>(`/programs/${programId}`, { method: 'DELETE' }),
  )

export function useCreateLender() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string }) => api<Lender>('/lenders', { method: 'POST', ...json(body) }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.lenders }),
  })
}

// --- PDF ingestion -----------------------------------------------------------------------------

const ingesting = (status: string | undefined) => status === 'uploaded' || status === 'extracting'

export const useIngestionJobs = () =>
  useQuery({
    queryKey: keys.ingestion,
    queryFn: () => api<IngestionJob[]>('/ingestion'),
    refetchInterval: (query) => (query.state.data?.some((j) => ingesting(j.status)) ? 2000 : false),
  })

export const useIngestionJob = (id: string | undefined) =>
  useQuery({
    queryKey: keys.ingestionJob(id ?? ''),
    queryFn: () => api<IngestionJob>(`/ingestion/${id}`),
    enabled: Boolean(id),
    refetchInterval: (query) => (ingesting(query.state.data?.status) ? 1500 : false),
  })

/** Multipart upload: the one request that does not go through the JSON helper. */
export function useUploadGuidelines() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: async (input: { file: File; lenderId?: string; newLenderName?: string }) => {
      const body = new FormData()
      body.append('file', input.file)
      if (input.lenderId) body.append('lender_id', input.lenderId)
      if (input.newLenderName) body.append('new_lender_name', input.newLenderName)
      const response = await fetch('/api/ingestion', { method: 'POST', body })
      if (!response.ok) {
        const detail: unknown = await response.json().catch(() => null)
        const message =
          detail && typeof detail === 'object' && 'detail' in detail
            ? ((detail as { detail: { message?: string } }).detail.message ?? response.statusText)
            : response.statusText
        throw new ApiError(response.status, message, detail)
      }
      return (await response.json()) as IngestionJob
    },
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.ingestion })
      void client.invalidateQueries({ queryKey: keys.lenders })
    },
  })
}

export function useRetryIngestion() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => api<IngestionJob>(`/ingestion/${id}/retry`, { method: 'POST' }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.ingestion }),
  })
}
