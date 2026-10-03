import { useCallback, useEffect, useState } from 'react'
import { api } from './api'

/** Load `path` and expose { data, error, reload }. Re-fetches when `path` changes. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, path: null })
  const reload = useCallback(() => api(path).then(
    data => setState({ data, error: null, path }),
    error => setState(s => ({ ...s, error, path })),
  ), [path])
  useEffect(() => { reload() }, [reload])
  // Keep showing the previous data while a new path loads, so filters don't flash.
  return { data: state.data, error: state.error, loading: state.path !== path, reload }
}
