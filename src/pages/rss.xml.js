import rss from '@astrojs/rss';
import { getCollection } from 'astro:content';
import { SITE_DESCRIPTION, SITE_TITLE } from '../consts';

export async function GET(context) {
	const posts = (await getCollection('blog')).sort(
		(a, b) => new Date(b.data.pubDate).valueOf() - new Date(a.data.pubDate).valueOf(),
	);

	const baseUrl = context.site || new URL('https://fabrica-seo.vercel.app');

	return rss({
		title: SITE_TITLE,
		description: SITE_DESCRIPTION,
		site: baseUrl,
		xmlns: {
			media: 'http://search.yahoo.com/mrss/',
			atom: 'http://www.w3.org/2005/Atom',
		},
		customData: `<language>es-ES</language>`,
		items: posts.map((post) => {
			// URL absoluta de la imagen de portada (heroImage) para Pinterest, FB y OpenGraph scrapers
			const absoluteHeroImage = post.data.heroImage
				? (post.data.heroImage.startsWith('http://') || post.data.heroImage.startsWith('https://')
					? post.data.heroImage
					: new URL(post.data.heroImage, baseUrl).toString())
				: '';

			// Categorías y keywords expuestas como tags para generación automática de hashtags en X
			const categories = Array.from(
				new Set([post.data.category, post.data.keyword].filter(Boolean)),
			);

			// Inyección de etiquetas de medios estándar en RSS 2.0 (enclosure + Media RSS)
			const customData = absoluteHeroImage
				? `<enclosure url="${absoluteHeroImage}" length="0" type="image/jpeg" />` +
				  `<media:content url="${absoluteHeroImage}" medium="image" />`
				: '';

			return {
				title: post.data.title,
				pubDate: post.data.pubDate,
				description: post.data.description, // Excerpt ligero para optimizar tiempo de parseo y payload
				link: `/blog/${post.id}/`,
				categories,
				customData,
			};
		}),
	});
}
