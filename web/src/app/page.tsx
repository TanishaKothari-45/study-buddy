"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { PageWrapper } from "@/components/layout/PageWrapper";
import Link from "next/link";
import {
  ArrowRight,
  FileText,
  Upload,
  Database,
  ClipboardList,
  PenTool,
  MessageSquare,
} from "lucide-react";

const features = [
  {
    label: "Upload materials",
    description: "Add PDFs, images, and notes to your knowledge base.",
    icon: Upload,
    href: "/upload",
    iconColor: "text-violet-500",
    iconBg: "bg-violet-50 dark:bg-violet-900/20",
  },
  {
    label: "Evaluate answer",
    description: "Get detailed feedback on your handwritten answers.",
    icon: FileText,
    href: "/evaluate",
    iconColor: "text-rose-500",
    iconBg: "bg-rose-50 dark:bg-rose-900/20",
  },
  {
    label: "Prelims mock test",
    description: "Take AI-generated quizzes based on your study topics.",
    icon: ClipboardList,
    href: "/mock-test",
    iconColor: "text-blue-600",
    iconBg: "bg-blue-50 dark:bg-blue-900/20",
  },
  {
    label: "Mains answer",
    description: "Generate model answers with diagrams and citations.",
    icon: PenTool,
    href: "/mains-answer",
    iconColor: "text-purple-600",
    iconBg: "bg-purple-50 dark:bg-purple-900/20",
  },
  {
    label: "Chat / Q&A",
    description: "Ask questions and clear doubts about your topics.",
    icon: MessageSquare,
    href: "/chat",
    iconColor: "text-emerald-600",
    iconBg: "bg-emerald-50 dark:bg-emerald-900/20",
  },
  {
    label: "Training data",
    description: "Manage examples to improve AI performance.",
    icon: Database,
    href: "/training-data",
    iconColor: "text-orange-500",
    iconBg: "bg-orange-50 dark:bg-orange-900/20",
  },
];

export default function Home() {
  return (
    <PageWrapper className="max-w-5xl mx-auto space-y-10">
      {/* Hero */}
      <div className="animate-fade-up space-y-3 pt-2">
        <p className="text-xs font-semibold tracking-widest text-amber-600 uppercase">
          UPSC Study Assistant
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-[var(--text)]">
          Your study buddy, powered by AI
        </h1>
        <p className="text-[var(--text-muted)] leading-relaxed max-w-xl">
          Upload your notes, generate practice tests, write model answers, and
          chat with your personal study assistant. Everything in one place.
        </p>
      </div>

      {/* Feature cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {features.map((feature, idx) => (
          <Link
            key={feature.href}
            href={feature.href}
            className={`block group animate-fade-up animate-fade-up-delay-${Math.min(idx + 1, 6)}`}
          >
            <Card className="h-full hover:shadow-warm-sm hover:border-[var(--text-faint)] transition-all duration-200">
              <CardHeader className="pb-3">
                <div className={`w-9 h-9 rounded-lg ${feature.iconBg} flex items-center justify-center mb-3`}>
                  <feature.icon className={`w-5 h-5 ${feature.iconColor}`} />
                </div>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold text-[var(--text)]">
                    {feature.label}
                  </CardTitle>
                  <ArrowRight className="w-4 h-4 text-[var(--text-faint)] group-hover:text-amber-600 group-hover:translate-x-0.5 transition-all duration-150" />
                </div>
              </CardHeader>
              <CardContent className="pt-0">
                <CardDescription className="text-xs leading-relaxed">
                  {feature.description}
                </CardDescription>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </PageWrapper>
  );
}
