import { NextRequest, NextResponse } from 'next/server';

export const runtime = 'edge'; // Use edge runtime for faster cold starts

// This is called by Vercel Cron
export async function GET(request: NextRequest) {
    // Verify the request is from Vercel Cron
    const authHeader = request.headers.get('authorization');
    const cronSecret = process.env.CRON_SECRET;

    if (!cronSecret) {
        return NextResponse.json(
            { error: 'CRON_SECRET not configured' },
            { status: 500 }
        );
    }

    if (authHeader !== `Bearer ${cronSecret}`) {
        return NextResponse.json(
            { error: 'Unauthorized' },
            { status: 401 }
        );
    }

    // Call your Python backend
    const backendUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

    try {
        const response = await fetch(
            `${backendUrl}/api/cron/trigger-monthly-current-affairs`,
            {
                method: 'GET',
                headers: {
                    'Authorization': `Bearer ${cronSecret}`,
                },
            }
        );

        const data = await response.json();

        if (!response.ok) {
            return NextResponse.json(
                { error: 'Backend cron job failed', details: data },
                { status: response.status }
            );
        }

        return NextResponse.json({
            success: true,
            message: 'Cron job triggered successfully',
            backendResponse: data,
        });
    } catch (error) {
        return NextResponse.json(
            {
                error: 'Failed to trigger backend cron job',
                details: error instanceof Error ? error.message : 'Unknown error'
            },
            { status: 500 }
        );
    }
}
