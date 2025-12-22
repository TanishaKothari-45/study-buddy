"use client";

import { Button } from "@/components/ui/button";
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
  MessageSquare
} from "lucide-react";

export default function Home() {
  return (
    <PageWrapper className="max-w-7xl mx-auto space-y-8">
      <div className="flex flex-col space-y-2">
        <h1 className="text-4xl font-bold tracking-tight text-foreground bg-clip-text text-transparent bg-gradient-to-r from-primary to-primary/60">
          Study Buddy AI
        </h1>
        <p className="text-lg text-muted-foreground">
          Your AI-powered geography study companion is ready.
        </p>
      </div>

      {/* Quick Actions Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        <Link href="/upload" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <Upload className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Upload Materials</CardTitle>
              <CardDescription>
                Add PDFs, images, and notes to your knowledge base.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/evaluate" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <FileText className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Evaluate Answer</CardTitle>
              <CardDescription>
                Get detailed feedback and scoring on your handwritten answers.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/mock-test" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <ClipboardList className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Prelims Mock Test</CardTitle>
              <CardDescription>
                Take AI-generated quizzes based on your study topics.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/mains-answer" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <PenTool className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Mains Answer Gen</CardTitle>
              <CardDescription>
                Generate model answers with diagrams and citations.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/chat" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <MessageSquare className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Chat / Q&A</CardTitle>
              <CardDescription>
                Ask questions and clear doubts about Geography Topics.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/training-data" className="block group">
          <Card className="h-full transition-all hover:shadow-md hover:border-primary/50">
            <CardHeader>
              <Database className="w-8 h-8 text-primary mb-2 group-hover:scale-110 transition-transform" />
              <CardTitle>Training Data</CardTitle>
              <CardDescription>
                Manage examples to improve AI performance.
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>
      </div>
    </PageWrapper>
  );
}
