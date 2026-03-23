import { useState } from 'react';
import type { NLAnswer } from '../types';

interface NLAnswerBannerProps {
  answer: NLAnswer;
  query?: string;
}

export default function NLAnswerBanner({ answer }: NLAnswerBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  const [copied, setCopied] = useState(false);

  if (dismissed) return null;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(answer.answer);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mb-5 rounded-xl border border-accent-blue/20 bg-gradient-to-br from-blue-50/80 to-indigo-50/50 dark:from-blue-950/30 dark:to-indigo-950/20 dark:border-accent-blue/25 overflow-hidden animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-3.5 pb-2">
        <div className="flex items-center gap-2">
          <div className="flex items-center justify-center w-6 h-6 rounded-full bg-accent-blue/15">
            <svg className="w-3.5 h-3.5 text-accent-blue" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.347.346A3.5 3.5 0 0114.5 20.5H9.5a3.5 3.5 0 01-2.471-1.026l-.347-.346z" />
            </svg>
          </div>
          <span className="text-xs font-semibold text-accent-blue uppercase tracking-wider">
            AI Answer
          </span>
          <span className="text-xs text-gray-400 dark:text-gray-500 font-normal normal-case tracking-normal">
            · Extracted from your documents
          </span>
        </div>
        <button
          onClick={() => setDismissed(true)}
          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors p-1 rounded"
          title="Dismiss"
        >
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Answer text */}
      <div className="px-4 pb-3">
        <p className="text-sm text-gray-700 dark:text-gray-200 leading-relaxed">
          {answer.answer}
        </p>
      </div>

      {/* Footer */}
      <div className="px-4 pb-3 flex items-center gap-3">
        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 text-xs text-gray-400 hover:text-accent-blue transition-colors"
        >
          {copied ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              Copied
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
              </svg>
              Copy answer
            </>
          )}
        </button>
        <span className="text-xs text-gray-300 dark:text-gray-600">·</span>
        <span className="text-xs text-gray-400 dark:text-gray-500">
          Scroll down to see source documents
        </span>
      </div>
    </div>
  );
}
