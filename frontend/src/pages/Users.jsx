// src/pages/Users.jsx
import { useState, useEffect } from 'react'
import { usersApi } from '../api/client'
import { useAuth } from '../context/AuthContext'

export default function Users() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [editUser, setEditUser] = useState(null)
  const [editForm, setEditForm] = useState({ username: '', email: '', password: '' })
  const [saveLoading, setSaveLoading] = useState(false)
  const [deleteId, setDeleteId] = useState(null)

  useEffect(() => { fetchUsers() }, [])

  async function fetchUsers() {
    setLoading(true)
    try {
      setUsers(await usersApi.list())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function openEdit(u) {
    setEditUser(u)
    setEditForm({ username: u.username, email: u.email, password: '' })
  }

  async function handleSave(e) {
    e.preventDefault()
    setSaveLoading(true)
    try {
      const payload = { username: editForm.username, email: editForm.email }
      if (editForm.password) payload.password = editForm.password
      await usersApi.update(editUser.id, payload)
      setEditUser(null)
      fetchUsers()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaveLoading(false)
    }
  }

  async function handleDelete() {
    try {
      await usersApi.delete(deleteId)
      setDeleteId(null)
      fetchUsers()
    } catch (err) {
      setError(err.message)
      setDeleteId(null)
    }
  }

  return (
    <>
      <div className="page-header">
        <h1 className="page-title">Users</h1>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      <div className="card">
        {loading ? (
          <div className="empty-state">Loading…</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Username</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Joined</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.id}>
                    <td className="text-muted">{u.id}</td>
                    <td>
                      <span style={{ fontWeight: 500 }}>{u.username}</span>
                      {u.id === me?.id && <span style={{ marginLeft: 6, fontSize: 11, background: '#eef2ff', color: 'var(--primary)', borderRadius: 4, padding: '1px 6px' }}>You</span>}
                    </td>
                    <td className="text-muted">{u.email}</td>
                    <td>
                      <span className={`badge ${u.role === 'admin' ? 'badge-p3' : 'badge-todo'}`}>{u.role}</span>
                    </td>
                    <td>
                      <span className={`badge ${u.is_active ? 'badge-done' : 'badge-p3'}`}>
                        {u.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="text-muted">{new Date(u.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="actions">
                        <button className="btn btn-ghost btn-sm" onClick={() => openEdit(u)}
                          disabled={me?.role !== 'admin' && u.id !== me?.id}>Edit</button>
                        <button className="btn btn-danger btn-sm" onClick={() => setDeleteId(u.id)}
                          disabled={u.id === me?.id || me?.role !== 'admin'}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Edit modal */}
      {editUser && (
        <div className="modal-overlay" onClick={e => e.target === e.currentTarget && setEditUser(null)}>
          <div className="modal">
            <div className="modal-title">Edit User</div>
            <form onSubmit={handleSave}>
              <div className="form-group">
                <label className="form-label">Username</label>
                <input className="form-control" value={editForm.username}
                  onChange={e => setEditForm(f => ({ ...f, username: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">Email</label>
                <input className="form-control" type="email" value={editForm.email}
                  onChange={e => setEditForm(f => ({ ...f, email: e.target.value }))} required />
              </div>
              <div className="form-group">
                <label className="form-label">New Password <span className="text-muted">(leave blank to keep)</span></label>
                <input className="form-control" type="password" value={editForm.password}
                  onChange={e => setEditForm(f => ({ ...f, password: e.target.value }))} placeholder="••••••••" />
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setEditUser(null)}>Cancel</button>
                <button type="submit" className="btn btn-primary" disabled={saveLoading}>
                  {saveLoading ? <span className="spinner" /> : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Delete confirm */}
      {deleteId && (
        <div className="modal-overlay">
          <div className="modal" style={{ maxWidth: 360 }}>
            <div className="modal-title">Delete user?</div>
            <p style={{ color: 'var(--muted)', fontSize: 14 }}>All their tasks will remain but be unowned.</p>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setDeleteId(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleDelete}>Delete</button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
