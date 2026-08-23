import React from "react";

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch() {
    console.error("前端运行时错误，已显示安全恢复页面。");
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <section
          className="pt-28 pb-12 min-h-screen flex items-center justify-center"
          role="alert"
          aria-label="页面暂时不可用"
        >
          <div className="text-center">
            <h1 className="text-red-500 text-xl mb-4">页面暂时不可用</h1>
            <p className="text-gray-700 dark:text-gray-300 mb-4">
              页面遇到问题，请重新加载后再试。
            </p>
            <button
              onClick={this.handleReload}
              className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            >
              重新加载
            </button>
          </div>
        </section>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
