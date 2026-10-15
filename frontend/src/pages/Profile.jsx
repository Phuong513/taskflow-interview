// src/pages/Profile.jsx
import { useState } from 'react'
import { usersApi } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useNavigate } from 'react-router-dom'

export default function Profile() {
  const { user, logout, refreshUser } = useAuth()
  const navigate = useNavigate()
  const [form, setForm] = useState({ username: user?.username || '', email: user?.email || '', password: '' })
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [error, setError] = useState('')

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    setSuccess('')
    setError('')
    try {
      const payload = { username: form.username, email: form.email }
      if (form.password) payload.password = form.password
      await usersApi.update(user.id, payload)
      if (payload.password) {
        logout()
        navigate('/login')
        return
      }
      await refreshUser()
      setSuccess('Profile updated successfully.')
      setForm(f => ({ ...f, password: '' }))
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">My Profile</h1>
      </div>

      <div className="card" style={{ maxWidth: 480 }}>
        <div className="card-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 28, paddingBottom: 24, borderBottom: '1px solid var(--border)' }}>
            <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700 }}>
              {user?.username?.[0]?.toUpperCase()}
            </div>
            <div>
              <div style={{ fontWeight: 600 }}>{user?.username}</div>
              <div className="text-muted">{user?.email}</div>
              <span className={`badge ${user?.role === 'admin' ? 'badge-p3' : 'badge-todo'}`} style={{ marginTop: 4 }}>{user?.role}</span>
            </div>
          </div>

          {success && <div className="alert alert-success">{success}</div>}
          {error && <div className="alert alert-error">{error}</div>}

          <form onSubmit={handleSubmit}>
            <div className="form-group">
              <label className="form-label">Username</label>
              <input className="form-control" value={form.username}
                onChange={e => setForm(f => ({ ...f, username: e.target.value }))} required />
            </div>
            <div className="form-group">
              <label className="form-label">Email</label>
              <input className="form-control" type="email" value={form.email}
                onChange={e => setForm(f => ({ ...f, email: e.target.value }))} required />
            </div>
            <div className="form-group">
              <label className="form-label">New Password <span className="text-muted">(leave blank to keep; changing it signs you out)</span></label>
              <input className="form-control" type="password" value={form.password}
                onChange={e => setForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" />
            </div>
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? <span className="spinner" /> : 'Update profile'}
            </button>
          </form>
        </div>
      </div>
    </>
  )
}
