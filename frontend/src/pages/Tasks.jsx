// src/pages/Tasks.jsx
import { useState, useEffect, useCallback } from 'react'
import { tasksApi } from '../api/client'
import TaskModal from '../components/TaskModal'
import { useAuth } from '../context/AuthContext'

const PRIORITY_LABELS = { 1: 'Low', 2: 'Medium', 3: 'High' }
const STATUS_LABELS = { todo: 'Todo', in_progress: 'In Progress', done: 'Done' }

function formatDate(dt) {
  if (!dt) return '—'
  return new Date(dt).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

export default function Tasks() {
  const { user } = useAuth()
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [searchQ, setSearchQ] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [modalTask, setModalTask] = useState(undefined)   // undefined=closed, null=new, obj=edit
  const [deleteId, setDeleteId] = useState(null)
  const [confirmLoading, setConfirmLoading] = useState(false)

  const fetchTasks = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      let data
      if (searchQ.trim()) {
        data = await tasksApi.search(searchQ.trim())
      } else {
        data = await tasksApi.list(filterStatus ? { status: filterStatus } : {})
      }
      setTasks(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [filterStatus, searchQ])

  useEffect(() => { fetchTasks() }, [fetchTasks])

  async function handleSave(payload) {
    if (modalTask?.id) {
      await tasksApi.update(modalTask.id, payload)
    } else {
      await tasksApi.create(payload)
    }
    fetchTasks()
  }

  async function handleDelete() {
    setConfirmLoading(true)
    try {
      await tasksApi.delete(deleteId)
      setDeleteId(null)
      fetchTasks()
    } catch (err) {
      setError(err.message)
    } finally {
      setConfirmLoading(false)
    }
  }

  function handleSearch(e) {
    e.preventDefault()
    setSearchQ(searchInput)
    setFilterStatus('')
  }

  function clearSearch() {
    setSearchInput('')
    setSearchQ('')
  }

  const stats = {
    total: tasks.length,
    todo: tasks.filter(t => t.status === 'todo').length,
    in_progress: tasks.filter(t => t.status === 'in_progress').length,
    done: tasks.filter(t => t.status === 'done').length,
  }

  return (
    <>
      {/* Stats */}
      <div className="stats-row">
        {[
          { label: 'Total', value: stats.total, color: 'var(--primary)' },
          { label: 'Todo', value: stats.todo, color: '#2b6cb0' },
          { label: 'In Progress', value: stats.in_progress, color: '#744210' },
          { label: 'Done', value: stats.done, color: 'var(--success)' },
        ].map(s => (
          <div className="stat-card" key={s.label}>
            <div className="stat-label">{s.label}</div>
            <div className="stat-value" style={{ color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      <div className="page-header">
        <h1 className="page-title">Tasks</h1>
        <button className="btn btn-primary" onClick={() => setModalTask(null)}>+ New Task</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {/* Filters */}
      <div className="filter-bar">
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: 8 }}>
          <input className="form-control" placeholder="Search tasks…" value={searchInput}
            onChange={e => setSearchInput(e.target.value)} />
          <button className="btn btn-ghost btn-sm" type="submit">Search</button>
          {searchQ && <button className="btn btn-ghost btn-sm" type="button" onClick={clearSearch}>✕ Clear</button>}
        </form>
        {!searchQ && (
          <select className="form-control" value={filterStatus}
            onChange={e => setFilterStatus(e.target.value)} style={{ minWidth: 140 }}>
            <option value="">All statuses</option>
            <option value="todo">Todo</option>
            <option value="in_progress">In Progress</option>
            <option value="done">Done</option>
          </select>
        )}
      </div>

      <div className="card">
        {loading ? (
          <div className="empty-state">Loading…</div>
        ) : tasks.length === 0 ? (
          <div className="empty-state">
            <div style={{ fontSize: 32, marginBottom: 8 }}>📋</div>
            No tasks found.{' '}
            <span style={{ cursor: 'pointer', color: 'var(--primary)' }} onClick={() => setModalTask(null)}>
              Create one
            </span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>#</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Due</th>
                  <th>Tags</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {tasks.map(task => (
                  <tr key={task.id}>
                    <td className="text-muted">{task.id}</td>
                    <td>
                      <div style={{ fontWeight: 500 }}>{task.title}</div>
                      {task.description && <div className="text-muted" style={{ marginTop: 2 }}>{task.description.slice(0, 60)}{task.description.length > 60 && '…'}</div>}
                    </td>
                    <td><span className={`badge badge-${task.status}`}>{STATUS_LABELS[task.status]}</span></td>
                    <td><span className={`badge badge-p${task.priority}`}>{PRIORITY_LABELS[task.priority]}</span></td>
                    <td className="text-muted">{formatDate(task.due_date)}</td>
                    <td>
                      {task.tags
                        ? task.tags.split(',').map(t => (
                            <span key={t} style={{ background: '#eef2ff', color: 'var(--primary)', borderRadius: 4, padding: '1px 7px', fontSize: 12, marginRight: 4 }}>{t.trim()}</span>
                          ))
                        : <span className="text-muted">—</span>}
                    </td>
                    <td>
                      <div className="actions">
                        <button className="btn btn-ghost btn-sm" onClick={() => setModalTask(task)}
                          disabled={user?.role !== 'admin' && task.owner_id !== user?.id}>Edit</button>
                        <button className="btn btn-danger btn-sm" onClick={() => setDeleteId(task.id)}
                          disabled={user?.role !== 'admin' && task.owner_id !== user?.id}>Delete</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Create / Edit modal */}
      {modalTask !== undefined && (
        <TaskModal
          task={modalTask}
          onSave={handleSave}
          onClose={() => setModalTask(undefined)}
        />
      )}

      {/* Delete confirm modal */}
      {deleteId && (
        <div className="modal-overlay">
          <div className="modal" style={{ maxWidth: 360 }}>
            <div className="modal-title">Delete task?</div>
            <p style={{ color: 'var(--muted)', fontSize: 14 }}>This action cannot be undone.</p>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setDeleteId(null)}>Cancel</button>
              <button className="btn btn-danger" onClick={handleDelete} disabled={confirmLoading}>
                {confirmLoading ? <span className="spinner" /> : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
