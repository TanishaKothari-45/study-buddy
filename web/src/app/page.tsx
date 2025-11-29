import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { ArrowRight, FileText, Upload, Database } from "lucide-react";

export default function Home() {
  return (
    <div className="p-8 space-y-8">
      <div className="flex flex-col space-y-2">
        <h1 className="text-4xl font-bold tracking-tight text-gray-900">
          Welcome back, Student!
        </h1>
        <p className="text-lg text-muted-foreground">
          Your AI-powered geography study companion is ready.
        </p>
      </div>

      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        <Card className="hover:shadow-lg transition-shadow border-t-4 border-t-pink-600">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-6 w-6 text-pink-600" />
              Evaluate Answer
            </CardTitle>
            <CardDescription>
              Get detailed feedback on your handwritten answers
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-gray-600">
              Upload your answer sheets and get instant AI evaluation with improved versions and structural feedback.
            </p>
            <Link href="/evaluate">
              <Button className="w-full group">
                Start Evaluation
                <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card className="hover:shadow-lg transition-shadow border-t-4 border-t-violet-600">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Upload className="h-6 w-6 text-violet-600" />
              Upload Materials
            </CardTitle>
            <CardDescription>
              Add new study materials to your knowledge base
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-gray-600">
              Upload PDFs, textbooks, and notes to enhance the AI's knowledge base for better answers.
            </p>
            <Link href="/upload">
              <Button variant="outline" className="w-full group">
                Upload Files
                <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
          </CardContent>
        </Card>

        <Card className="hover:shadow-lg transition-shadow border-t-4 border-t-orange-600">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Database className="h-6 w-6 text-orange-600" />
              Training Data
            </CardTitle>
            <CardDescription>
              Manage training examples for few-shot learning
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="mb-4 text-sm text-gray-600">
              View and manage the example answers used to train the AI on your specific writing style.
            </p>
            <Link href="/training-data">
              <Button variant="outline" className="w-full group">
                Manage Data
                <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
