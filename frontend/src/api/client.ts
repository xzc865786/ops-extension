import axios from 'axios'

const api = axios.create({
  baseURL: '/ext/api/v1',
  withCredentials: true,
})

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      // session expired
    }
    return Promise.reject(err)
  }
)

export default api
