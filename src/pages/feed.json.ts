import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';

export const GET: APIRoute = async (context) => {
	const posts = (await getCollection('blog')).sort(
		(a, b) => new Date(b.data.pubDate).valueOf() - new Date(a.data.pubDate).valueOf(),
	);

	const baseUrl = context.site || new URL('https://fabrica-seo.vercel.app');

	const feed = {
		version: 'https://jsonfeed.org/version/1.1',
		title: SITE_TITLE,
		home_page_url: baseUrl.toString(),
		feed_url: new URL('/feed.json', baseUrl).toString(),
		description: SITE_DESCRIPTION,
		language: 'es-ES',
		items: posts.map((post) => {
			// URL absoluta del artículo
			const absoluteUrl = new URL(`/blog/${post.id}/`, baseUrl).toString();

			// URL absoluta de la portada (hero image) para Pinterest, FB y OpenGraph
			const absoluteHeroImage = post.data.heroImage
				? (post.data.heroImage.startsWith('http://') || post.data.heroImage.startsWith('https://')
					? post.data.heroImage
					: new URL(post.data.heroImage, baseUrl).toString())
				: null;

			// Extracción de tags y categorías como array para los hashtags en X (Twitter)
			const tags = Array.from(
				new Set([post.data.category, post.data.keyword].filter(Boolean) as string[]),
			);

			return {
				id: absoluteUrl,
				url: absoluteUrl,
				title: post.data.title,
				description: post.data.description, // Excerpt ligero sin HTML completo
				pubDate: post.data.pubDate.toISOString(),
				date_published: post.data.pubDate.toISOString(),
				image: absoluteHeroImage,
				heroImage: absoluteHeroImage,
				tags: tags,
				categories: tags,
				category: post.data.category,
				keyword: post.data.keyword || null,
			};
		}),
	};

	return new Response(JSON.stringify(feed, null, 2), {
		headers: {
			'Content-Type': 'application/json; charset=utf-8',
			'Cache-Control': 'public, max-age=3600',
		},
	});
};
