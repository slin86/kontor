import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'

import { aiApi, type Job } from '../aiApi'
import { isActive, JOB_LABEL, JOB_PATH, useJobParam } from '../jobs'
import { primary } from './ui'

/** Notices for AI jobs in the corner of every page: running, ready to open, or failed. */
export function JobNotices() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { jobId } = useJobParam()
  const jobs = useQuery({
    queryKey: ['ai', 'jobs'],
    queryFn: aiApi.jobs,
    retry: false,
    refetchInterval: (q) => (q.state.data?.some(isActive) ? 3000 : false),
  })
  // the page that shows a job reports on it itself
  const shown = (jobs.data ?? []).filter((j) => j.id !== jobId)
  if (shown.length === 0) return null

  async function dismiss(job: Job) {
    await aiApi.dismissJob(job.id)
    await qc.invalidateQueries({ queryKey: ['ai'] })
  }

  return (
    <div role="status" aria-live="polite" className="fixed bottom-4 right-4 z-50 w-[min(24rem,calc(100vw-2rem))] space-y-2">
      {shown.map((job) => (
        <div key={job.id} className={`border-l-4 bg-karte p-3 text-sm shadow-lg ${job.status === 'failed' ? 'border-bake' : 'border-elbe'}`}>
          <p className="font-medium">
            {JOB_LABEL[job.kind]} „{job.filename}“
          </p>
          <p className="mt-0.5 text-tinte-weich">
            {job.status === 'done' && 'Fertig gelesen.'}
            {job.status === 'failed' && (job.error ?? 'Das hat nicht geklappt.')}
            {job.status === 'queued' && 'Wartet in der Schlange.'}
            {job.status === 'running' && 'Wird gelesen …'}
            {job.status === 'waiting' && 'Wartet auf den KI-Server …'}
          </p>
          <div className="mt-2 flex items-center gap-3">
            {job.status === 'done' && (
              <button type="button" className={`${primary} text-sm`} onClick={() => navigate(`${JOB_PATH[job.kind]}?job=${job.id}`)}>
                Ergebnis ansehen
              </button>
            )}
            <button type="button" className="font-medium text-elbe-dunkel hover:underline" onClick={() => dismiss(job)}>
              {isActive(job) ? 'Abbrechen' : 'Verwerfen'}
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
