import React, { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { CalendarDays, Clock3, Sparkles, BookOpen, Layers3, Trophy, RotateCcw, CheckCircle2, Target, Zap, ChevronRight } from 'lucide-react';
import { useStudy } from '../../context/StudyContext';
import { fetchTopics } from '../../services/api';

const getToday = () => {
  const d = new Date();
  const offset = d.getTimezoneOffset();
  const local = new Date(d.getTime() - offset * 60000);
  return local.toISOString().slice(0, 10);
};

const addDays = (dateString, amount) => {
  const d = new Date(`${dateString}T00:00:00`);
  d.setDate(d.getDate() + amount);
  return d;
};

const formatDate = (date) => date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

const distributeTopics = (topics, days) => {
  if (!topics.length) return Array.from({ length: days }, () => []);
  const buckets = Array.from({ length: Math.max(1, days) }, () => []);
  topics.forEach((topic, index) => {
    const bucket = index % Math.max(1, days);
    buckets[bucket].push(topic);
  });
  return buckets;
};

export const ExamPulseView = () => {
  const { docData, topicsData, setTopicsData } = useStudy();
  const [loading, setLoading] = useState(!topicsData);
  const [examDate, setExamDate] = useState(() => localStorage.getItem('easy-learn-exam-date') || '');
  const [showSettings, setShowSettings] = useState(!examDate);
  const [tempDate, setTempDate] = useState(examDate || getToday());

  useEffect(() => {
    if (topicsData || !docData) return;
    const loadTopics = async () => {
      try {
        setLoading(true);
        const data = await fetchTopics(docData.file_id);
        setTopicsData(data.topics || []);
      } catch (error) {
        console.error('Exam Pulse topic loading failed:', error);
      } finally {
        setLoading(false);
      }
    };
    loadTopics();
  }, [docData, topicsData, setTopicsData]);

  const daysLeft = useMemo(() => {
    if (!examDate) return 0;
    const today = new Date(`${getToday()}T00:00:00`);
    const exam = new Date(`${examDate}T00:00:00`);
    return Math.max(0, Math.ceil((exam - today) / 86400000));
  }, [examDate]);

  const safeDays = Math.max(1, Math.min(daysLeft || 1, 14));
  const topics = topicsData || [];

  const plan = useMemo(() => {
    if (!topics.length) return [];
    const sorted = [...topics].sort((a, b) => (b.importance_percentage || 0) - (a.importance_percentage || 0));
    const studyDays = Math.max(1, safeDays - (safeDays >= 3 ? 1 : 0));
    const buckets = distributeTopics(sorted, studyDays);
    return Array.from({ length: safeDays }, (_, index) => {
      const isFinal = index === safeDays - 1 && safeDays >= 3;
      const assigned = isFinal ? [] : (buckets[index] || []);
      const date = examDate ? addDays(getToday(), index) : null;
      const importance = assigned.reduce((sum, topic) => sum + (topic.importance_percentage || 0), 0);
      const hours = isFinal ? Math.max(1.5, Math.min(3, topics.length * 0.25)) : Math.max(1, Math.min(3, assigned.length * 1.15 + (importance / 100) * 0.8));
      return {
        day: index + 1,
        date,
        isFinal,
        topics: assigned,
        hours: Number(hours.toFixed(1)),
        title: isFinal ? 'Final Revision & Exam Readiness' : index === 0 ? 'Foundations & Core Principles' : index === safeDays - 2 && safeDays >= 3 ? 'Advanced Practice & Recall' : `Deep Dive: Study Block ${index + 1}`,
        activities: isFinal ? ['Rapid revision', 'Active recall', 'Mock exam / weak-area check'] : ['Read key sections', 'Active recall synthesis', 'Checkpoint verification']
      };
    });
  }, [topics, safeDays, examDate]);

  const totalHours = plan.reduce((sum, item) => sum + item.hours, 0).toFixed(1);
  const todayPlan = plan[0];

  const saveExamDate = () => {
    const chosen = tempDate || getToday();
    localStorage.setItem('easy-learn-exam-date', chosen);
    setExamDate(chosen);
    setShowSettings(false);
  };

  if (loading) {
    return <div className="min-h-[50vh] flex items-center justify-center text-slate-400 text-sm font-mono">Building your Exam Pulse from the document topics...</div>;
  }

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="glass-panel rounded-3xl p-5 sm:p-7">
        <div className="flex flex-col xl:flex-row xl:items-start xl:justify-between gap-5">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-mono font-bold uppercase tracking-[0.2em] text-indigo-400">
              <Sparkles className="w-4 h-4" /> Exam Pulse Active
            </div>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-2">YOUR EXAM PULSE</h2>
            <p className="text-xs text-slate-400 mt-2 max-w-xl">A document-aware study timetable that turns the remaining days before your exam into focused study blocks.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button onClick={() => setShowSettings(true)} className="px-4 py-2.5 rounded-xl bg-indigo-500/15 border border-indigo-400/30 text-indigo-200 text-xs font-semibold flex items-center gap-2 hover:bg-indigo-500/25 transition-colors">
              <CalendarDays className="w-4 h-4" /> Change Exam Date
            </button>
            <div className="px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 text-xs font-mono flex items-center gap-2">
              <Clock3 className="w-4 h-4 text-cyan-400" /> {daysLeft > 0 ? `EXAM IN ${daysLeft} DAYS` : examDate ? 'EXAM DAY' : 'SET EXAM DATE'}
            </div>
            <div className="px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 text-xs font-mono flex items-center gap-2">
              <BookOpen className="w-4 h-4 text-indigo-400" /> {topics.length} Topics
            </div>
            <div className="px-4 py-2.5 rounded-xl bg-slate-900/80 border border-slate-800 text-slate-300 text-xs font-mono flex items-center gap-2">
              <Layers3 className="w-4 h-4 text-purple-400" /> Est. {totalHours}h Total
            </div>
          </div>
        </div>
        <div className="mt-5 pt-4 border-t border-slate-800 flex items-center justify-between gap-3 text-[11px] font-mono">
          <span className="text-slate-500">“YOUR TIME IS LIMITED. YOUR LEARNING DOESN'T HAVE TO BE.”</span>
          <span className="text-indigo-400 font-bold">PULSE READY</span>
        </div>
      </motion.section>

      {!examDate && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="rounded-2xl border border-indigo-500/20 bg-indigo-500/5 p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div><p className="text-sm font-semibold text-slate-200">Set your exam date to generate the timetable.</p><p className="text-xs text-slate-500 mt-1">Your uploaded topics are already available; only the remaining time is needed.</p></div>
          <button onClick={() => setShowSettings(true)} className="shrink-0 px-4 py-2 rounded-lg bg-indigo-500 text-white text-xs font-bold">Set Exam Date</button>
        </motion.div>
      )}

      <section className="rounded-2xl bg-slate-950/80 border border-slate-800/80 p-4 sm:p-5 overflow-x-auto">
        <div className="min-w-[760px] flex items-center gap-2">
          {plan.map((item, index) => (
            <React.Fragment key={item.day}>
              <div className={`min-w-[120px] px-4 py-4 rounded-2xl border ${index === 0 ? 'border-indigo-400 bg-indigo-500/15' : item.isFinal ? 'border-amber-400/30 bg-amber-400/5' : 'border-slate-800 bg-slate-900/70'}`}>
                <div className="text-[10px] font-mono uppercase text-slate-500">Day {item.day}</div>
                <div className="text-xs font-bold text-slate-200 mt-1 line-clamp-2">{item.isFinal ? 'Final Revision' : item.topics[0]?.name || 'Revision'}</div>
              </div>
              {index < plan.length - 1 && <div className="h-px w-8 bg-slate-700 shrink-0" />}
            </React.Fragment>
          ))}
          <div className="min-w-[100px] flex flex-col items-center gap-1 text-amber-300"><Trophy className="w-6 h-6" /><span className="text-[10px] font-mono">EXAM</span></div>
        </div>
      </section>

      {todayPlan && (
        <div className="grid lg:grid-cols-[1fr_1.05fr] gap-5">
          <section className="rounded-2xl bg-slate-950/80 border border-slate-800/80 p-5 sm:p-6 relative overflow-hidden">
            <div className="absolute -right-20 -top-20 w-56 h-56 rounded-full bg-indigo-500/10 blur-3xl" />
            <div className="relative">
              <div className="flex items-center justify-between"><span className="text-[10px] font-mono uppercase tracking-widest text-indigo-400">Day 1 Constellation Chart</span><span className="text-[10px] px-2 py-1 rounded bg-slate-900 border border-slate-800 text-slate-400">{topics.length ? 'Document Topics' : 'Waiting for Topics'}</span></div>
              <div className="relative h-[280px] mt-4 overflow-hidden rounded-xl bg-slate-950/60 border border-slate-900">
                <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-14 rounded-full bg-indigo-400/15 border border-indigo-300/40 shadow-[0_0_35px_rgba(99,102,241,0.45)] flex items-center justify-center text-[9px] font-mono text-indigo-200">DAY 1</div>
                {todayPlan.topics.slice(0, 6).map((topic, i) => {
                  const angle = (i / Math.max(1, Math.min(todayPlan.topics.length, 6))) * Math.PI * 2 - Math.PI / 2;
                  const x = 50 + Math.cos(angle) * 34;
                  const y = 50 + Math.sin(angle) * 36;
                  return <div key={topic.id || topic.name} className="absolute -translate-x-1/2 -translate-y-1/2 text-center" style={{ left: `${x}%`, top: `${y}%` }}><div className="w-3 h-3 rounded-full bg-indigo-300 shadow-[0_0_18px_rgba(129,140,248,0.8)] mx-auto" /><span className="block mt-2 text-[9px] text-slate-400 max-w-[100px] truncate">{topic.name}</span></div>;
                })}
                {todayPlan.topics.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-600 font-mono">Final revision mode</div>}
              </div>
              <p className="text-[10px] text-slate-500 font-mono mt-3">Topic nodes are generated from the uploaded document's important-topic analysis.</p>
            </div>
          </section>

          <section className="rounded-2xl bg-slate-950/80 border border-slate-800/80 p-5 sm:p-6">
            <div className="text-[10px] font-mono uppercase tracking-widest text-indigo-400">Day 1 Pulse Plan</div>
            <h3 className="text-2xl font-extrabold text-white mt-1">{todayPlan.title}</h3>
            <div className="mt-5 grid sm:grid-cols-2 gap-3">
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800"><div className="text-[10px] uppercase text-slate-500 font-mono">Pulse Goal</div><p className="text-sm text-slate-300 mt-2">Build clear conceptual understanding of the highest-priority material.</p></div>
              <div className="p-4 rounded-xl bg-slate-900 border border-slate-800"><div className="text-[10px] uppercase text-slate-500 font-mono">Study Time</div><p className="text-lg font-bold text-white mt-2">{todayPlan.hours} hours</p></div>
            </div>
            <div className="mt-5"><div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mb-3">Topics to Master</div><div className="flex flex-wrap gap-2">{todayPlan.topics.length ? todayPlan.topics.map(topic => <span key={topic.id || topic.name} className="px-3 py-2 rounded-lg bg-indigo-500/10 border border-indigo-400/20 text-xs text-indigo-100">{topic.name}</span>) : <span className="text-xs text-slate-500">Use today for revision and recall.</span>}</div></div>
            <div className="mt-5"><div className="text-[10px] uppercase tracking-widest text-slate-500 font-mono mb-3">Study Activities</div><div className="grid sm:grid-cols-3 gap-2">{todayPlan.activities.map((activity, i) => <div key={activity} className="p-3 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-300 flex items-center gap-2"><CheckCircle2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />{activity}</div>)}</div></div>
          </section>
        </div>
      )}

      <section className="space-y-3">
        <div className="flex items-center justify-between"><div><h3 className="text-xl font-bold text-white">Your Study Timeline</h3><p className="text-xs text-slate-500 mt-1">Each day is generated from your document topics and the time remaining.</p></div><Zap className="w-5 h-5 text-indigo-400" /></div>
        <div className="space-y-3">
          {plan.map((item, index) => (
            <motion.div key={item.day} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * 0.04 }} className={`rounded-2xl border p-4 sm:p-5 ${index === 0 ? 'border-indigo-400/30 bg-indigo-500/5' : 'border-slate-800 bg-slate-950/70'}`}>
              <div className="flex flex-col md:flex-row md:items-center gap-4">
                <div className="w-20 shrink-0"><div className="text-[10px] uppercase font-mono text-slate-500">Day</div><div className="text-2xl font-extrabold text-white">{item.day}</div>{item.date && <div className="text-[10px] text-slate-500">{formatDate(item.date)}</div>}</div>
                <div className="flex-1"><h4 className="text-base font-bold text-slate-100">{item.title}</h4><div className="flex flex-wrap gap-2 mt-2">{item.topics.length ? item.topics.map(topic => <span key={topic.id || topic.name} className="text-[10px] px-2 py-1 rounded-md bg-slate-900 border border-slate-800 text-slate-400">{topic.name}</span>) : <span className="text-xs text-slate-500">Revision, recall and exam readiness</span>}</div></div>
                <div className="flex items-center gap-3 shrink-0"><div className="text-right"><div className="text-[10px] uppercase font-mono text-slate-500">Est.</div><div className="text-sm font-bold text-slate-200">{item.hours}h</div></div><ChevronRight className="w-4 h-4 text-slate-600" /></div>
              </div>
            </motion.div>
          ))}
        </div>
      </section>

      <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-4 flex items-start gap-3 text-xs text-slate-400"><Target className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" /><p><strong className="text-slate-300">How the plan works:</strong> higher-importance topics are scheduled earlier, while the final day is reserved for revision and exam readiness. You can change the exam date anytime.</p></div>

      {showSettings && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <motion.div initial={{ opacity: 0, scale: .96, y: 10 }} animate={{ opacity: 1, scale: 1, y: 0 }} className="w-full max-w-md rounded-2xl bg-slate-950 border border-slate-800 p-6 shadow-2xl">
            <div className="flex items-center gap-3"><CalendarDays className="w-5 h-5 text-indigo-400" /><div><h3 className="text-lg font-bold text-white">Set Your Exam Date</h3><p className="text-xs text-slate-500">EASY-LEARN will rebuild the study timeline automatically.</p></div></div>
            <input type="date" min={getToday()} value={tempDate} onChange={e => setTempDate(e.target.value)} className="mt-6 w-full px-4 py-3 rounded-xl bg-slate-900 border border-slate-700 text-white text-sm outline-none focus:border-indigo-400" />
            <div className="flex justify-end gap-2 mt-5"><button onClick={() => setShowSettings(false)} className="px-4 py-2 rounded-lg text-xs text-slate-400 hover:text-white">Cancel</button><button onClick={saveExamDate} className="px-4 py-2 rounded-lg bg-indigo-500 text-white text-xs font-bold">Generate Pulse</button></div>
          </motion.div>
        </div>
      )}
    </div>
  );
};
