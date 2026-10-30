import React, { Component, ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode | ((error: Error) => ReactNode)
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  }

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  public componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught error in child component:', error, errorInfo)
  }

  public render() {
    if (this.state.hasError) {
      if (typeof this.props.fallback === 'function') {
        return this.props.fallback(this.state.error || new Error('Unknown error'))
      }
      return this.props.fallback || (
        <div className="w-full h-full p-4 flex flex-col items-center justify-center bg-neutral-950 text-neutral-400 text-xs font-mono border border-red-900/30">
          <span className="text-red-400 font-bold mb-1">Visualization Unavailable</span>
          <span className="text-[10px] text-neutral-500 max-w-md text-center">
            {this.state.error?.message || 'Component failed to render'}
          </span>
        </div>
      )
    }

    return this.props.children
  }
}
