import React from "react";
import { ArrowLeft, Home } from "lucide-react";
import { useNavigate } from "react-router-dom";

const NotFoundPage = ({ styles, isDark }) => {
  const navigate = useNavigate();

  return (
    <div className={`min-h-screen ${styles.bgSecondary} px-5 pt-32 pb-20`}>
      <section className="mx-auto flex w-full max-w-3xl flex-col items-start gap-8">
        <div className="space-y-4">
          <p className={isDark ? "text-orange-300" : "text-[#189BCC]"}>
            404
          </p>
          <h1 className={`text-4xl font-semibold leading-tight md:text-6xl ${styles.text}`}>
            这个页面不存在
          </h1>
          <p className={`max-w-xl text-base leading-7 ${styles.textMuted}`}>
            可能是链接已经失效，或者地址输入有误。
          </p>
        </div>

        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => navigate(-1)}
            className={`inline-flex items-center gap-2 rounded-xl border px-5 py-3 text-sm font-medium transition-transform hover:-translate-y-0.5 ${styles.border} ${styles.text}`}
          >
            <ArrowLeft size={18} />
            返回上一页
          </button>
          <button
            type="button"
            onClick={() => navigate("/")}
            className={`inline-flex items-center gap-2 rounded-xl px-5 py-3 text-sm font-medium text-white transition-transform hover:-translate-y-0.5 ${
              isDark ? "bg-orange-600 hover:bg-orange-500" : "bg-[#189BCC] hover:bg-[#147aa6]"
            }`}
          >
            <Home size={18} />
            回到首页
          </button>
        </div>
      </section>
    </div>
  );
};

export default NotFoundPage;
