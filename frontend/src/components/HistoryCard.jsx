import React, { useState, useEffect } from "react";
import { Calendar, RefreshCw } from "lucide-react";

const HistoryCard = ({ isDark }) => {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const date = new Date();
      const mm = String(date.getMonth() + 1).padStart(2, '0');
      const dd = String(date.getDate()).padStart(2, '0');

      const response = await fetch(`https://zh.wikipedia.org/api/rest_v1/feed/onthisday/events/${mm}/${dd}`);
      const data = await response.json();

      if (data && data.events) {
        // Shuffle and pick 3 events
        const shuffled = data.events.sort(() => 0.5 - Math.random());
        setEvents(shuffled.slice(0, 3));
      }
    } catch (err) {
      console.error("Failed to fetch history:", err);
      setError("无法获取历史数据");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, []);

  return (
    <div className={`history-card relative ${isDark ? 'text-gray-200' : 'text-gray-800'}`}>
      <div className="history-card-head">
        <div>
          <span className="history-kicker">历史上的今天</span>
          <h3>历史上的今天</h3>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); fetchHistory(); }}
          className="history-refresh"
          title="换一批"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="history-timeline min-h-[200px]">
        {loading ? (
          <div className="flex items-center justify-center h-40">
            <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full"></div>
          </div>
        ) : error ? (
          <div className="text-center py-8 text-sm text-gray-500">{error}</div>
        ) : (
          events.map((event, idx) => (
            <div key={idx} className="history-event">
              <span className="history-year">
                {event.year}
              </span>
              <p>
                {event.text}
              </p>
            </div>
          ))
        )}
      </div>

      <div className="history-source">
        <Calendar size={13} />
        <span>来源：Wikipedia</span>
      </div>
    </div>
  );
};

export default HistoryCard;
