import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'

import { aiApi, type Job, type JobDetail, type JobKind } from './aiApi'

/** Where the result of a job is reviewed. */
export const JOB_PATH: Record<JobKind, string> = {
  statement: '/posten',
  contract: '/posten',
  financing: '/finanzierungen',
  depot: '/ist',
}

export const JOB_LABEL: Record<JobKind, string> = {
  statement: 'Kontoauszug',
  contract: 'Dokument',
  financing: 'Vertrag',
  depot: 'Broker-Datei',
}

export const isActive = (job: Pick<Job, 'status'>) => job.status === 'queued' || job.status === 'running' || job.status === 'waiting'

/** The job a page is showing, taken from ``?job=`` so that a notice can link straight to it. */
export function useJobParam() {
  const [params, setParams] = useSearchParams()
  return {
    jobId: params.get('job'),
    open: (id: string) =>
      setParams(
        (p) => {
          p.set('job', id)
          return p
        },
        { replace: true },
      ),
    close: () =>
      setParams(
        (p) => {
          p.delete('job')
          return p
        },
        { replace: true },
      ),
  }
}

/** A job and, while it runs, a refresh every few seconds. */
export function useJob<T>(jobId: string | null) {
  return useQuery({
    queryKey: ['ai', 'job', jobId],
    queryFn: () => aiApi.job(jobId!) as Promise<JobDetail<T>>,
    enabled: !!jobId,
    retry: false,
    refetchInterval: (q) => (q.state.data && isActive(q.state.data) ? 2500 : false),
  })
}

/** Uploads a file as a background job and shows it on this page. */
export function useStartJob(kind: JobKind) {
  const qc = useQueryClient()
  const { open } = useJobParam()
  return useMutation({
    mutationFn: (v: { file: File; mapping?: Record<string, number>; person_id?: number }) =>
      aiApi.startJob(kind, v.file, { mapping: v.mapping, person_id: v.person_id }),
    onSuccess: async (job) => {
      await qc.invalidateQueries({ queryKey: ['ai', 'jobs'] })
      open(job.id)
    },
  })
}

/** Forgets a job on the server and leaves it on this page. */
export function useFinishJob() {
  const qc = useQueryClient()
  const { close } = useJobParam()
  return async (id: string | null) => {
    close()
    if (!id) return
    try {
      await aiApi.dismissJob(id)
    } finally {
      await qc.invalidateQueries({ queryKey: ['ai'] })
    }
  }
}

export function JobProgress({ job }: { job: Pick<Job, 'status' | 'error'> }) {
  if (job.status === 'failed') {
    return (
      <p role="alert" className="text-sm font-medium text-bake">
        {job.error ?? 'Das hat nicht geklappt.'}
      </p>
    )
  }
  if (job.status === 'done') return null
  const text =
    job.status === 'queued'
      ? 'In der Warteschlange. Ein anderes Dokument wird gerade gelesen.'
      : job.status === 'waiting'
        ? 'Warte auf den KI-Server. Ist der Rechner noch aus oder lädt er das Modell? Es geht automatisch weiter, sobald er bereit ist.'
        : 'Das Dokument wird gelesen. Das kann einige Minuten dauern.'
  return (
    <p className="text-sm text-tinte-weich" aria-live="polite">
      {text} Du kannst die Seite wechseln, Kontor meldet sich, wenn es fertig ist.
    </p>
  )
}
